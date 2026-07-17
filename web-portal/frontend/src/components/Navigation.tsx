/**
 * Navigation Component
 * Shared top navbar rendered once in Layout.tsx for every page.
 */
import { Link } from 'react-router-dom';
import { Menu, Search, User } from 'lucide-react';
import logo from '../assets/virtual-lab-logo-white.svg';

export default function Navigation() {
  return (
    <header className="flex h-14 flex-shrink-0 items-center justify-between gap-6 bg-[#0B0B0B] px-6">
      {/* Left: hamburger + logo */}
      <div className="flex flex-shrink-0 items-center gap-[18px]">
        <button
          type="button"
          aria-label="Menu"
          className="flex cursor-pointer items-center text-white"
        >
          <Menu size={20} strokeWidth={2} />
        </button>
        <Link to="/" className="flex items-center">
          <img src={logo} alt="Virtual Lab" className="block h-[22px] w-auto" />
        </Link>
      </div>

      {/* Center: search */}
      <div className="flex max-w-[420px] flex-1 items-center gap-2 rounded-lg bg-white/[0.08] px-3 py-2">
        <Search size={15} strokeWidth={2} className="text-white/50" />
        <span className="flex-1 text-[13px] text-white/50">Search labs, courses...</span>
        <span className="rounded border border-white/20 px-[5px] py-px text-[11px] text-white/35">
          ⌘K
        </span>
      </div>

      {/* Right: avatar */}
      <button
        type="button"
        aria-label="Account"
        className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full border border-white/35 text-white/85"
      >
        <User size={17} strokeWidth={2} />
      </button>
    </header>
  );
}
