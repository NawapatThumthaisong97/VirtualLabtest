/**
 * Routes
 * All application routes with RootLayout
 */
import { createBrowserRouter } from 'react-router-dom';
import RootLayout from '../components/Layout.tsx';
import HomePage from '../pages/Home.tsx';
import ImagesPage from '../pages/Images.tsx';
import CoursesPage from '../pages/Courses.tsx';
import CourseDetailPage from '../pages/CourseDetail.tsx';
import LabDetailPage from '../pages/LabDetail.tsx';
import LoginPage from '../pages/Login.tsx';

export const router = createBrowserRouter([
  // Full-bleed auth page: no navbar, no footer
  {
    path: '/login',
    element: <LoginPage />,
  },
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
]);

export default router;

