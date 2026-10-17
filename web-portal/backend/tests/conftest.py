"""
Fixture ที่ใช้ร่วมกันทุกเทส + ตารางสรุปผลรายเคสท้ายการรัน

เทสกลุ่ม builder ไม่ต่อ DB และไม่เรียก SkyPilot จริง แค่สร้าง task config แล้วตรวจผล

DB (fixture db): Postgres ชื่อ virtual_lab_test (model ใช้ UUID / JSONB / enum / exclusion
constraint ของ Postgres ใช้ SQLite ไม่ได้)
- สร้าง schema ใหม่จาก model ทุกครั้งที่เริ่มรัน
- แต่ละเทสอยู่ใน transaction ที่ rollback ทิ้งตอนจบ ข้อมูลไม่ค้าง
  (join_transaction_mode="create_savepoint" ทำให้ db.commit() ในโค้ดจริงกลายเป็น savepoint)
- ต่อ DB ไม่ได้ → เทสที่ใช้ db ถูก skip ส่วนเทสที่ไม่ใช้ DB ยังรันได้
เปลี่ยน DB ได้ด้วย env TEST_DATABASE_URL (ชื่อ DB ต้องลงท้ายด้วย _test กันลบข้อมูลจริง)

ตารางสรุป: Group = บรรทัดแรกของ docstring ของ class, Case = บรรทัดแรกของ docstring ของเทส
(ไม่มี docstring จะใช้ชื่อ class / ฟังก์ชันแทน) ปิดได้ด้วย `pytest --no-case-table`
"""
import os
from collections import Counter

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import app.models  # noqa: F401  ให้ทุก table อยู่ใน Base.metadata
from app.configs.db import Base
from app.configs.settings import settings
from app.models.lab_image import LabImage
from app.services.session_service import SessionService

ECR_HOST = "123456789012.dkr-ecr.ap-southeast-1.on.aws"
AMI = "ami-0123456789abcdef0"
REGISTRY = "10.0.0.1:5001"


# ค่าที่เทสยังต้องใช้จาก .env (หา DB ทดสอบจาก DATABASE_URL ดู fixture db_engine)
SETTINGS_FROM_DOTENV = {"DATABASE_URL"}


@pytest.fixture(autouse=True)
def default_settings(monkeypatch):
    """ทุกเทสเริ่มจากค่า default ในโค้ด ไม่ใช่ .env ของเครื่องที่รัน

    .env ของ dev เปิดฟีเจอร์ไว้ทดลอง (LAB_ISOLATION_ENABLED / WARM_POD_ENABLED / PREWARM_LEAD_MINUTES ฯลฯ)
    ถ้าเทสอ่านค่าพวกนี้ ผลจะขึ้นกับว่าเครื่องไหนรัน — เทสที่ต้องการค่าอื่นให้ monkeypatch เองในเทส
    """
    defaults = type(settings)(_env_file=None)
    for name in type(settings).model_fields:
        if name not in SETTINGS_FROM_DOTENV:
            monkeypatch.setattr(settings, name, getattr(defaults, name))


@pytest.fixture
def service():
    # builder ไม่ใช้ db / repository เลยส่ง None ได้
    return SessionService(db=None, session_repository=None,
                          lab_repository=None, lab_image_repository=None)


@pytest.fixture
def make_image():
    """สร้าง LabImage (ไม่ลง DB) ค่าตั้งต้นเหมือน lab music-lab ที่ใช้อยู่จริง"""
    def _make(**overrides) -> LabImage:
        fields = dict(
            repository="skypilot/music-lab",
            tag="lab-01",
            cpu_requirement="2+",
            memory_requirement="4+",
            disk_size=50,
            lifespan_minutes=60,
            exposed_ports=[8080, 5173, 8443],
            entrypoint_script="/bin/bash /run.sh",
            workdir=None,
            env_vars={"IDE_PASSWORD": "musiclab"},
        )
        fields.update(overrides)
        return LabImage(**fields)
    return _make


@pytest.fixture(autouse=True)
def fixed_settings(monkeypatch):
    """ไม่ให้ผลเทสขึ้นกับ .env ของแต่ละเครื่อง"""
    monkeypatch.setenv("DOCKER_REGISTRY_HOST", REGISTRY)
    monkeypatch.setattr(settings, "AWS_REGION", "ap-southeast-1")
    monkeypatch.setattr(settings, "AWS_LAB_AMI", AMI)
    monkeypatch.setattr(settings, "AWS_INSTANCE_TYPE", "m7i-flex.large")
    monkeypatch.setattr(settings, "AWS_DISK_SIZE", 30)
    monkeypatch.setattr(settings, "ECR_REGISTRY_HOST", ECR_HOST)


# ---------------------------------------------------------------- DB เทส

def _test_db_url() -> str:
    url = os.getenv("TEST_DATABASE_URL") or make_url(settings.DATABASE_URL).set(
        database="virtual_lab_test"
    ).render_as_string(hide_password=False)
    if not make_url(url).database.endswith("_test"):
        raise RuntimeError(f"test DB name must end with _test: {make_url(url).database}")
    return url


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(_test_db_url())
    try:
        with engine.connect():
            pass
    except OperationalError as e:
        pytest.skip(f"test database not available: {e.orig}")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


# ---------------------------------------------------------------- ตารางสรุปผล

_RESULT_COLORS = {
    "passed": {"green": True},
    "failed": {"red": True, "bold": True},
    "error": {"red": True, "bold": True},
    "skipped": {"yellow": True},
    "xfailed": {"yellow": True},
    "xpassed": {"yellow": True},
}
_results: dict[str, tuple[str, str, str]] = {}  # nodeid -> (group, case, outcome)


def _first_line(doc):
    lines = (doc or "").strip().splitlines()
    return lines[0].strip() if lines else ""


def pytest_addoption(parser):
    parser.addoption("--no-case-table", action="store_true",
                     help="ไม่แสดงตารางสรุปผลรายเคสท้ายการรัน")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    report = (yield).get_result()
    case = _first_line(item.function.__doc__) or item.name
    if getattr(item, "callspec", None):
        case += f" [{item.callspec.id}]"
    report.case = case
    report.group = _first_line(item.cls.__doc__) or item.cls.__name__ if item.cls else item.module.__name__


def pytest_runtest_logreport(report):
    if not hasattr(report, "case"):
        return
    if report.when == "call":
        if hasattr(report, "wasxfail"):
            outcome = "xfailed" if report.skipped else "xpassed"
        else:
            outcome = report.outcome
    elif report.failed:
        outcome = "error"  # setup / teardown พัง
    elif report.skipped and report.when == "setup":
        outcome = "skipped"
    else:
        return
    _results[report.nodeid] = (report.group, report.case, outcome)


def pytest_terminal_summary(terminalreporter, config):
    if config.getoption("--no-case-table") or not _results:
        return
    headers = ("#", "Group", "Case", "Result")
    rows = [(str(i), group, case, outcome.upper())
            for i, (group, case, outcome) in enumerate(_results.values(), 1)]
    widths = [max(len(h), *(len(r[k]) for r in rows)) for k, h in enumerate(headers)]

    def line(cells):
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths)) + " |"

    tr = terminalreporter
    tr.section("test cases")
    tr.write_line(line(headers), bold=True)
    tr.write_line("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for row, (_, _, outcome) in zip(rows, _results.values()):
        tr.write_line(line(row), **_RESULT_COLORS[outcome])

    counts = Counter(outcome for _, _, outcome in _results.values())
    worst = next((o for o in ("error", "failed", "xpassed", "xfailed", "skipped") if counts[o]), "passed")
    summary = ", ".join(f"{n} {o}" for o, n in counts.most_common())
    tr.write_line(f"TOTAL {len(_results)}: {summary}", **{**_RESULT_COLORS[worst], "bold": True})
