/**
 * Navigation Component
 */
import { Link } from 'react-router-dom';

export default function Navigation() {
  return (
    <nav className="bg-white shadow border-b">
      <div className="max-w-7xl mx-auto px-4 py-0">
        <div className="flex justify-between h-16">
          <div className="flex items-center space-x-8">
            <Link to="/" className="font-bold text-xl">
              Virtual Lab
            </Link>
            <div className="hidden md:flex space-x-4">
              <Link
                to="/"
                className="px-3 py-2 rounded-md text-sm font-medium hover:bg-gray-100 transition"
              >
                Home
              </Link>
              <Link
                to="/images"
                className="px-3 py-2 rounded-md text-sm font-medium hover:bg-gray-100 transition"
              >
                Images
              </Link>
              <Link
                to="/courses"
                className="px-3 py-2 rounded-md text-sm font-medium hover:bg-gray-100 transition"
              >
                Courses
              </Link>
            </div>
          </div>
        </div>
      </div>
    </nav>
  );
}
