/**
 * Admin Dashboard (/admin) — หน้าแรกของ admin หลัง login, UI จาก Design system introduction
 * ข้อมูลจริงจาก /api/v1/admin/* ดึงใหม่ทุก 30 วินาที
 */
import { useQuery } from '@tanstack/react-query';
import { colors } from '../components/admin/theme';
import Navbar from '../components/admin/Navbar';
import DashboardHeader from '../components/admin/DashboardHeader';
import SystemTable from '../components/admin/SystemTable';
import InfraVisualizer from '../components/admin/InfraVisualizer';
import LogExplorer from '../components/admin/LogExplorer';
import BillingEstimate from '../components/admin/BillingEstimate';
import BillingUsage from '../components/admin/BillingUsage';
import { adminBillingService, adminDashboardService } from '../services/adminDashboard';

const REFRESH_MS = 30_000;

export default function AdminDashboardPage() {
  const status = useQuery({
    queryKey: ['admin', 'system-status'],
    queryFn: adminDashboardService.getSystemStatus,
    refetchInterval: REFRESH_MS,
  });
  const map = useQuery({
    queryKey: ['admin', 'infra-map'],
    queryFn: adminDashboardService.getInfraMap,
    refetchInterval: REFRESH_MS,
  });
  const usage = useQuery({
    queryKey: ['admin', 'rooms-usage'],
    queryFn: adminDashboardService.getRoomUsage,
    refetchInterval: REFRESH_MS,
  });
  const billing = useQuery({
    queryKey: ['admin', 'billing-summary'],
    queryFn: adminBillingService.getSummary,
    refetchInterval: REFRESH_MS,
  });
  const monthly = useQuery({
    queryKey: ['admin', 'billing-monthly'],
    queryFn: adminBillingService.getMonthly,
    refetchInterval: REFRESH_MS,
  });
  const failed = [status, map, usage, billing, monthly].some((q) => q.isError);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', fontFamily: "'Inter', sans-serif" }}>
      <Navbar />
      <DashboardHeader />

      {failed && (
        <div style={{ background: colors.cellRed, color: colors.text, padding: '8px 32px', fontSize: 13 }}>
          ดึงข้อมูลบางส่วนไม่สำเร็จ — จะลองใหม่อัตโนมัติทุก 30 วินาที
        </div>
      )}

      <main
        style={{
          background: colors.pageBg,
          flex: 1,
          padding: '24px 32px',
          display: 'grid',
          gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)',
          gap: 32,
          alignContent: 'start',
          alignItems: 'start',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 32 }}>
          <SystemTable data={status.data} />
          <div id="billing" style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 24, scrollMarginTop: 16 }}>
            <BillingEstimate data={billing.data} />
            <BillingUsage monthly={monthly.data} summary={billing.data} />
          </div>
          <div id="logs" style={{ scrollMarginTop: 16 }}>
            <LogExplorer />
          </div>
        </div>

        <InfraVisualizer map={map.data} usage={usage.data} status={status.data} />
      </main>
    </div>
  );
}
