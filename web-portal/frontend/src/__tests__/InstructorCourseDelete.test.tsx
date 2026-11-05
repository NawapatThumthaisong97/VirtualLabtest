import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import InstructorCoursePage from '../pages/InstructorCourse';
import { courseService } from '../services/course';
import { labService, type LabSummary } from '../services/lab';
import { labImageService } from '../services/labImage';
import { courseDocumentService } from '../services/courseDocument';
import * as AuthContextModule from '../contexts/AuthContext';

const labs: LabSummary[] = [
  { id: 'l1', title: 'OOP with Spring Boot', description: null, docUrl: null, orderNo: 1, dueAt: null,
    status: 'published', imageId: 'img1', progressStatus: null },
  { id: 'l2', title: 'OOP (AUTO)', description: null, docUrl: null, orderNo: 2, dueAt: null,
    status: 'draft', imageId: 'img1', progressStatus: null },
];

describe('Instructor Console: gear menu deletes a lab / its image', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(courseService, 'getById').mockResolvedValue({
      id: 'c1', code: 'SE301', name: 'Software Engineer', lecturerName: 'Kittipong', imageUrl: null,
      backgroundKey: null, iconKey: null, announcements: [],
    });
    vi.spyOn(labService, 'listByCourse').mockResolvedValue(labs);
    vi.spyOn(labImageService, 'listByCourse').mockResolvedValue([
      { id: 'img1', courseId: 'c1', repository: 'skypilot/music-lab', tag: 'lab-01', status: 'approved' } as never,
    ]);
    vi.spyOn(courseDocumentService, 'list').mockResolvedValue([]);
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 'u1', email: 'k@dome.tu.ac.th', name: 'Kittipong', studentId: null, role: 'instructor' },
      isLoading: false, isAuthenticated: true, login: vi.fn(), loginWithSSO: vi.fn(),
      handleSsoCallback: vi.fn(), logout: vi.fn(), refreshUser: vi.fn(),
    });
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={['/instructor/courses/c1']}>
          <Routes>
            <Route path="/instructor/courses/:courseId" element={<InstructorCoursePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it('delete lab: gear → ลบ lab นี้ → confirm → API, then notice', async () => {
    const del = vi.spyOn(labService, 'delete').mockResolvedValue();
    renderPage();
    fireEvent.click(await screen.findByText('OOP with Spring Boot'));
    fireEvent.click(screen.getByLabelText('Settings for OOP with Spring Boot'));
    fireEvent.click(screen.getByText('ลบ lab นี้'));
    await waitFor(() => expect(del).toHaveBeenCalledWith('l1'));
    expect(await screen.findByText('ลบ lab แล้ว')).toBeDefined();
  });

  it('delete image: confirm lists every lab using it, then reports detached labs', async () => {
    const remove = vi.spyOn(labImageService, 'remove').mockResolvedValue({ detachedLabs: 2 });
    renderPage();
    fireEvent.click(await screen.findByText('OOP with Spring Boot'));
    fireEvent.click(screen.getByLabelText('Settings for OOP with Spring Boot'));
    fireEvent.click(screen.getByText('ลบ image ของ lab นี้'));
    expect((window.confirm as unknown as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain('OOP with Spring Boot, OOP (AUTO)');
    await waitFor(() => expect(remove).toHaveBeenCalledWith('img1'));
    expect(await screen.findByText(/ปลดออกจาก 2 lab/)).toBeDefined();
  });
});
