/**
 * Routes
 * Application routes with Route Guards and Layouts
 */
import { createBrowserRouter } from 'react-router-dom';
import RootLayout from '../components/Layout.tsx';
import ProtectedRoute from '../components/ProtectedRoute.tsx';
import HomePage from '../pages/Home.tsx';
import ImagesPage from '../pages/Images.tsx';
import CoursesPage from '../pages/Courses.tsx';
import CourseDetailPage from '../pages/CourseDetail.tsx';
import LabDetailPage from '../pages/LabDetail.tsx';
import LoginPage from '../pages/Login.tsx';
import SSOCallbackPage from '../pages/SSOCallback.tsx';
import InstructorPage from '../pages/Instructor.tsx';
import AdminMonitorPage from '../pages/AdminMonitor.tsx';
import AdminDashboardPage from '../pages/AdminDashboard.tsx';
import ClassSchedulePage from '../pages/ClassSchedule.tsx';

export const router = createBrowserRouter([
  // Public auth pages: no navbar, no footer
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/auth/callback',
    element: <SSOCallbackPage />,
  },
  // Protected Application Routes
  {
    element: <ProtectedRoute />,
    children: [
      // Marketing / browsing pages: navbar + footer
      {
        element: <RootLayout />,
        children: [
          {
            path: '/',
            element: <HomePage />,
          },
          {
            path: '/images',
            element: <ImagesPage />,
          },
          {
            path: '/courses',
            element: <CoursesPage />,
          },
          {
            path: '/courses/:courseId',
            element: <CourseDetailPage />,
          },
        ],
      },
      // Instructor pages: navbar + footer, restricted to instructor & admin
      {
        element: <ProtectedRoute allowedRoles={['instructor', 'admin']} />,
        children: [
          {
            element: <RootLayout />,
            children: [
              {
                path: '/instructor',
                element: <InstructorPage />,
              },
            ],
          },
        ],
      },
      // Admin Monitor & SIEM Dashboard: restricted strictly to 'admin'
      {
        element: <ProtectedRoute allowedRoles={['admin']} />,
        children: [
          // Admin dashboard: layout ของตัวเอง (Design system) ไม่ใช้ navbar / footer ของหน้านักศึกษา
          {
            path: '/admin',
            element: <AdminDashboardPage />,
          },
          {
            path: '/admin/scheduler',
            element: <ClassSchedulePage />,
          },
          {
            element: <RootLayout />,
            children: [
              {
                path: '/admin/monitor',
                element: <AdminMonitorPage />,
              },
              {
                path: '/monitor',
                element: <AdminMonitorPage />,
              },
            ],
          },
        ],
      },
      // Lab workspace pages: navbar only, no footer
      {
        element: <RootLayout showFooter={false} />,
        children: [
          {
            path: '/labs/:labId',
            element: <LabDetailPage />,
          },
        ],
      },
    ],
  },
]);

export default router;
