/**
 * Root Layout Component
 * Main HTML structure and shared layout (like Next.js layout.tsx)
 */
import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Navigation from './Navigation.tsx';
import Footer from './Footer.tsx';

// Metadata configuration (similar to Next.js)
const APP_METADATA = {
  title: 'Virtual Lab',
  description: 'Virtual Lab Application',
  generator: 'vite',
  themeColor: '#ffffff',
  colorScheme: 'light',
} as const;

// Set metadata on mount
function setMetadata() {
  document.title = APP_METADATA.title;
  
  // Set description meta tag
  let metaDescription = document.querySelector('meta[name="description"]');
  if (!metaDescription) {
    metaDescription = document.createElement('meta');
    metaDescription.setAttribute('name', 'description');
    document.head.appendChild(metaDescription);
  }
  metaDescription.setAttribute('content', APP_METADATA.description);
  
  // Set theme color
  let metaThemeColor = document.querySelector('meta[name="theme-color"]');
  if (!metaThemeColor) {
    metaThemeColor = document.createElement('meta');
    metaThemeColor.setAttribute('name', 'theme-color');
    document.head.appendChild(metaThemeColor);
  }
  metaThemeColor.setAttribute('content', APP_METADATA.themeColor);
  
  // Set color scheme
  let metaColorScheme = document.querySelector('meta[name="color-scheme"]');
  if (!metaColorScheme) {
    metaColorScheme = document.createElement('meta');
    metaColorScheme.setAttribute('name', 'color-scheme');
    document.head.appendChild(metaColorScheme);
  }
  metaColorScheme.setAttribute('content', APP_METADATA.colorScheme);
}

export default function RootLayout() {
  useEffect(() => {
    setMetadata();
  }, []);

  return (
    <html lang="th" className="scroll-smooth">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="generator" content={APP_METADATA.generator} />
      </head>
      <body className="antialiased font-sans bg-white text-black">
        <div className="flex flex-col min-h-screen">
          <Navigation />
          <main className="flex-1">
            <Outlet />
          </main>
          <Footer />
        </div>
      </body>
    </html>
  );
}

