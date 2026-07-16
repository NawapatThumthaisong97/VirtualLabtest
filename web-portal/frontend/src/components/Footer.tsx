/**
 * Footer Component
 */

export default function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-black text-white py-8 border-t">
      <div className="max-w-7xl mx-auto px-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mb-8">
          <div>
            <h3 className="font-bold text-lg mb-4">Virtual Lab</h3>
            <p className="text-gray-400 text-sm">
              A modern virtual lab application built with React and TypeScript.
            </p>
          </div>
          <div>
            <h4 className="font-semibold mb-4">Quick Links</h4>
            <ul className="space-y-2 text-sm text-gray-400">
              <li><a href="/" className="hover:text-white transition">Home</a></li>
              <li><a href="/images" className="hover:text-white transition">Images</a></li>
              <li><a href="/courses" className="hover:text-white transition">Courses</a></li>
            </ul>
          </div>
          <div>
            <h4 className="font-semibold mb-4">Contact</h4>
            <p className="text-sm text-gray-400">
              Email: info@webportal.com
            </p>
          </div>
        </div>
        <div className="border-t border-gray-800 pt-8">
          <p className="text-center text-gray-400 text-sm">
            &copy; {currentYear} Virtual Lab. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
