import { Link, NavLink } from 'react-router-dom'

const navItems = [
  { label: 'Dashboard', to: '/' },
  { label: 'Chat', to: '/chat' },
  { label: 'Docs', to: '/docs' },
]

function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-(--border) bg-(--bg)/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Link to="/" className="flex items-center gap-2 no-underline">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-(--accent) text-sm font-semibold text-white">
            H
          </span>
          <span className="text-base font-semibold text-(--text-h)">
            HR Copilot
          </span>
        </Link>

        <nav className="hidden items-center gap-6 md:flex">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `text-sm no-underline transition-colors ${
                  isActive
                    ? 'text-(--text-h) font-medium'
                    : 'text-(--text) hover:text-(--text-h)'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <Link
          to="/login"
          className="rounded-lg border border-(--border) px-4 py-2 text-sm font-medium text-(--text-h) no-underline transition-colors hover:border-(--accent-border) hover:bg-(--accent-bg)"
        >
          Sign in
        </Link>
      </div>
    </header>
  )
}

export default Header
