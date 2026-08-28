/**
 * Routes
 * All application routes with RootLayout
 */
import { createBrowserRouter } from 'react-router-dom';
import RootLayout from '../components/Layout.tsx';
import HomePage from '../pages/Home.tsx';
import ImagesPage from '../pages/Images.tsx';
import CoursesPage from '../pages/Courses.tsx';
import LoginPage from '../pages/Login.tsx';

export const router = createBrowserRouter([
  // Full-bleed auth page: no navbar, no footer
  {
    path: '/login',
    element: <LoginPage />,
  },
  // Pages that share the navbar + footer chrome
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
]);

export default router;
