/**
 * Routes
 * All application routes with RootLayout
 */
import { createBrowserRouter } from 'react-router-dom';
import RootLayout from '../components/Layout.tsx';
import HomePage from '../pages/Home.tsx';
import ImagesPage from '../pages/Images.tsx';
import CoursesPage from '../pages/Courses.tsx';
import LabDetailPage from '../pages/LabDetail.tsx';

export const router = createBrowserRouter([
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
