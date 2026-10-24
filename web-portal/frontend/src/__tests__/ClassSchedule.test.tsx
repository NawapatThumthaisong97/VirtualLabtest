import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ClassSchedulePage from '../pages/ClassSchedule';
import * as AuthContextModule from '../contexts/AuthContext';

describe('ClassSchedule (/admin/scheduler)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'u1', email: 'admin@dome.tu.ac.th', name: 'Admin', studentId: null, role: 'admin' },
      isLoading: false,
      isAuthenticated: true,
      login: vi.fn(),
      loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(),
      logout: vi.fn(),
      refreshUser: vi.fn(),
    });
  });

  const renderPage = () => render(<MemoryRouter><ClassSchedulePage /></MemoryRouter>);

  it('says the data is sample data (no API yet)', () => {
    renderPage();
    expect(screen.getByText('Class Schedule')).toBeDefined();
    expect(screen.getByText(/ข้อมูลตัวอย่าง/)).toBeDefined();
  });

  it('request Detail opens the Class Scheduler form prefilled with the teacher request', () => {
    renderPage();
    fireEvent.click(screen.getByText('Class Request'));
    fireEvent.click(screen.getByLabelText('Open request from Dr. Napat Srisuk'));
    expect((screen.getByDisplayValue('React Fundamentals') as HTMLInputElement).value).toBe('React Fundamentals');
    expect(screen.getByDisplayValue('LC-107')).toBeDefined();
    expect(screen.getByText('Approve')).toBeDefined();
  });
});
