import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import HomePage from '../pages/Home';
import * as AuthContextModule from '../contexts/AuthContext';
import { coursesService } from '../services/courses';
import { activityService } from '../services/activity';

describe('Home tabs', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'u1', email: 'sophia.dav@dome.tu.ac.th', name: 'Sophia Davis', studentId: '6709616000', role: 'student' },
      isLoading: false, isAuthenticated: true, login: vi.fn(), loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(), logout: vi.fn(), refreshUser: vi.fn(),
    });
    vi.spyOn(coursesService, 'getAll').mockResolvedValue([]);
    vi.spyOn(activityService, 'getMine').mockResolvedValue([]);
  });

  const renderHome = () =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter><HomePage /></MemoryRouter>
      </QueryClientProvider>,
    );

  it('shows the support logo and the two glass cards with a mail link', () => {
    renderHome();
    fireEvent.click(screen.getByText('Help Desk'));
    expect(screen.getByAltText('Virtual Lab Support')).toBeDefined();
    expect(screen.getByText('Can’t run your lab?')).toBeDefined();
    expect(screen.getByText('VirtualLabSupport@gmail.com').getAttribute('href')).toBe('mailto:VirtualLabSupport@gmail.com');
  });

  it('service cards stay in the layout (hidden) on other tabs so the hero keeps its height', () => {
    renderHome();
    fireEvent.click(screen.getByText('Help Desk'));
    const hidden = screen.getByText('Virtual Environment').closest('[aria-hidden]');
    expect(hidden?.getAttribute('aria-hidden')).toBe('true');
    expect(hidden?.className).toContain('invisible');
  });
});
