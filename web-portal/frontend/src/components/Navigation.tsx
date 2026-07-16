/**
 * Navigation Component
 */
import { Link } from 'react-router-dom';

export default function Navigation() {
  return (
    <nav className="bg-white shadow border-b">
      <div className="max-w-7xl mx-auto px-1 py-0">
        <div className="flex justify-between items-center h-16">
          <Link to="/" className="flex items-center">
            <img
              src="/virtual-lab-logo-black.svg"
              alt="Virtual Lab Logo"
              className="h-70 w-70"
            />
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
    </nav>
  );
}
