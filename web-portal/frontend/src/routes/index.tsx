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

export const router = createBrowserRouter([
  // Public auth pages: no navbar, no footer
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/auth/callback',
    element: <SSOCallbackPage />,
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
      {
        path: '/instructor',
        element: <InstructorPage />,
      },
    ],
  },
  // Protected Application Routes (Acceptance Criteria 2)
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
