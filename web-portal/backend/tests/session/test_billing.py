"""
กลุ่ม 11: billing หน้า admin — บันทึกการใช้งานตอน session จบ, สรุปเดือน / budget, สวิตช์ burst AWS
(docs/ADMIN_MONITOR.md PR 3)
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.configs.settings import settings
from app.exceptions.domain import CloudBurstDisabledError
from app.models.session import SessionEndReason, SessionStatus
from app.models.usage_record import UsageRecord
from app.services import admin_billing_service as billing
from tests.session.test_warm_pod import OUTSIDE_IP, PETE_IP, k8s  # noqa: F401 (fixture)


@pytest.fixture(autouse=True)
def price(monkeypatch):
    monkeypatch.setattr(settings, "AWS_HOURLY_PRICE_USD", 0.12)
    monkeypatch.setattr(settings, "AWS_MONTHLY_BUDGET_USD", 200.0)
    monkeypatch.setattr(settings, "AWS_BUDGET_ALERT_PCT", 80)


def records(db, session):
    return db.query(UsageRecord).filter(UsageRecord.session_id == session.id).all()


class TestRecordUsage:
    """Session end writes one usage record (hours + AWS cost)"""

    def test_on_prem(self, svc, db, add_session):
        """Lab machine session 2 h -> 7200 s, not cloud, $0"""
        s = add_session(SessionStatus.RUNNING, started_ago=timedelta(hours=2))
        svc._end_session(s, SessionStatus.STOPPED, SessionEndReason.USER_DELETE)
        [r] = records(db, s)
        assert 7190 <= r.duration_seconds <= 7210
        assert (r.is_cloud_burst, float(r.est_cost_usd)) == (False, 0.0)
        assert 14380 <= r.cpu_seconds <= 14420   # image ขอ 2 CPU

    def test_aws_cost(self, svc, db, world, add_session):
        """AWS session 30 min -> 0.5 h x $0.12 = $0.06"""
        s = add_session(SessionStatus.RUNNING, lab=world.aws_lab, started_ago=timedelta(minutes=30))
        s.is_cloud = True
        svc._end_session(s, SessionStatus.STOPPED, SessionEndReason.EXPIRED)
        [r] = records(db, s)
        assert r.is_cloud_burst and float(r.est_cost_usd) == pytest.approx(0.06, abs=0.001)

    def test_once(self, svc, db, add_session):
        """Ending twice (e.g. reconciler after delete) -> still one record"""
        s = add_session(SessionStatus.RUNNING)
        svc._end_session(s, SessionStatus.STOPPED, SessionEndReason.USER_DELETE)
        svc._end_session(s, SessionStatus.STOPPED, SessionEndReason.LOST)
        assert len(records(db, s)) == 1


class TestSummary:
    """GET /admin/billing/summary: AWS $ vs budget, hours on-prem / AWS"""

    def end(self, svc, add_session, world, hours, cloud):
        s = add_session(SessionStatus.RUNNING, lab=world.aws_lab if cloud else None,
                        started_ago=timedelta(hours=hours), user=None)
        s.is_cloud = cloud
        svc._end_session(s, SessionStatus.STOPPED, SessionEndReason.USER_DELETE)

    def test_totals(self, svc, db, world, add_session):
        """Ended + still running sessions counted; share by hours"""
        self.end(svc, add_session, world, 3, cloud=False)
        self.end(svc, add_session, world, 1, cloud=True)
        running = add_session(SessionStatus.RUNNING, lab=world.aws_lab, started_ago=timedelta(hours=1),
                              cluster="music-lab-running")
        running.is_cloud = True
        db.commit()

        s = billing.get_billing_summary(db)

        assert s.on_prem.session_hours == pytest.approx(3, abs=0.01)
        assert s.aws.session_hours == pytest.approx(2, abs=0.01)
        assert s.aws.used_usd == pytest.approx(0.24, abs=0.01)
        assert (s.aws.instances_running, s.aws.alert, s.aws.source) == (1, "none", "estimate")
        assert (s.share.on_prem_pct, s.share.aws_pct) == (pytest.approx(60, abs=0.5), pytest.approx(40, abs=0.5))
        assert s.aws.forecast_usd >= s.aws.used_usd
        assert s.burst_enabled is True

    @pytest.mark.parametrize("budget,alert", [(0.3, "warn"), (0.1, "over")])
    def test_alert(self, svc, db, world, add_session, monkeypatch, budget, alert):
        """$0.24 used: budget $0.30 -> warn (80%), $0.10 -> over"""
        monkeypatch.setattr(settings, "AWS_MONTHLY_BUDGET_USD", budget)
        self.end(svc, add_session, world, 2, cloud=True)
        assert billing.get_billing_summary(db).aws.alert == alert

    def test_monthly(self, svc, db, world, add_session):
        """6 months old -> new, this month has the usage, others 0"""
        self.end(svc, add_session, world, 2, cloud=True)
        months = billing.get_billing_monthly(db, 6).months
        assert len(months) == 6
        assert months[-1].aws_hours == pytest.approx(2, abs=0.01)
        assert all(m.aws_hours == 0 for m in months[:-1])
        now = datetime.now(timezone.utc).astimezone(billing.BILLING_TZ)
        assert months[-1].month == f"{now.year:04d}-{now.month:02d}"


class TestBurstSwitch:
    """PATCH /admin/cloud/controls: burst off -> no EC2"""

    def test_default_on(self, db):
        """No row yet -> burst enabled"""
        assert billing.get_cloud_control(db).burst_enabled is True

    def test_off_blocks_aws(self, svc, db, world, fake_sky, k8s):
        """Burst off: Start from outside -> 409, nothing launched"""
        billing.set_burst(db, False, "เกิน budget", world.user.id)
        with pytest.raises(CloudBurstDisabledError):
            svc.create_session(world.user.id, world.k8s_lab.id, client_ip=OUTSIDE_IP)
        assert fake_sky.launched == []
        assert billing.get_cloud_control(db).reason == "เกิน budget"

    def test_off_lab_machine_still_works(self, svc, db, world, fake_sky, k8s, monkeypatch):
        """Burst off: Start from a lab machine still gets a pod"""
        monkeypatch.setattr(settings, "LAB_ISOLATION_ENABLED", True)
        billing.set_burst(db, False, None, world.user.id)
        result = svc.create_session(world.user.id, world.k8s_lab.id, client_ip=PETE_IP)
        assert result["node_name"] == "worker-pete"

    def test_back_on(self, svc, db, world, fake_sky, k8s):
        """Burst on again -> EC2 launch allowed"""
        billing.set_burst(db, False, None, world.user.id)
        billing.set_burst(db, True, None, world.user.id)
        svc.create_session(world.user.id, world.k8s_lab.id, client_ip=OUTSIDE_IP)
        assert len(fake_sky.launched) == 1
