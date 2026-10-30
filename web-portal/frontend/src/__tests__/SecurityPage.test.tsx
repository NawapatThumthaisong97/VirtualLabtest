import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const GRAFANA = 'http://100.125.244.48:30300';

async function renderPage(url: string, reachable: boolean) {
  vi.stubEnv('VITE_SIEM_GRAFANA_URL', url);
  vi.resetModules();
  vi.stubGlobal('fetch', vi.fn(() => (reachable ? Promise.resolve(new Response()) : Promise.reject(new TypeError('Failed to fetch')))));
  // resetModules → Navbar โหลด AuthContext ตัวใหม่ ต้อง spy ตัวที่ import หลัง reset
  const auth = await import('../contexts/AuthContext');
  vi.spyOn(auth, 'useAuth').mockReturnValue({
    user: { id: 'u1', email: 'admin@dome.tu.ac.th', name: 'Admin', studentId: null, role: 'admin' },
    isLoading: false, isAuthenticated: true, login: vi.fn(), loginWithSSO: vi.fn(),
    handleSsoCallback: vi.fn(), logout: vi.fn(), refreshUser: vi.fn(),
  });
  const { default: SecurityPage } = await import('../pages/SecurityPage');
  return render(<MemoryRouter><SecurityPage /></MemoryRouter>);
}

describe('SecurityPage (/admin/security)', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('embeds Threat Analytics in kiosk dark mode, tab switches to Command Center', async () => {
    await renderPage(GRAFANA, true);
    const frame = (await screen.findByTitle('Grafana SIEM')) as HTMLIFrameElement;
    expect(frame.src).toBe(`${GRAFANA}/d/vlab-siem-analytics?orgId=1&kiosk&theme=dark`);

    fireEvent.click(screen.getByText('Command Center'));
    expect(((await screen.findByTitle('Grafana SIEM')) as HTMLIFrameElement).src).toContain('/d/vlab-siem-5layer?');
    expect(screen.getByText('Open in Grafana ↗').getAttribute('href')).toContain('/d/vlab-siem-5layer?');
  });

  it('Grafana unreachable -> message + retry instead of a blank iframe', async () => {
    await renderPage(GRAFANA, false);
    expect(await screen.findByText('เปิด Grafana ไม่ได้')).toBeDefined();
    expect(screen.queryByTitle('Grafana SIEM')).toBeNull();
    expect(screen.getByText('ลองใหม่')).toBeDefined();
  });

  it('URL not set at build time -> says so, no request', async () => {
    await renderPage('', true);
    expect(screen.getByText('ยังไม่ได้ตั้ง VITE_SIEM_GRAFANA_URL ตอน build frontend')).toBeDefined();
    expect(fetch).not.toHaveBeenCalled();
  });
});
