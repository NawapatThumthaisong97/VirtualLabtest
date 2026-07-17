/**
 * Routes
 * All application routes with RootLayout
 */
import { createBrowserRouter } from 'react-router-dom';
import RootLayout from '../components/Layout.tsx';
import HomePage from '../pages/Home.tsx';
import ImagesPage from '../pages/Images.tsx';
import CoursesPage from '../pages/Courses.tsx';

export const router = createBrowserRouter([
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
