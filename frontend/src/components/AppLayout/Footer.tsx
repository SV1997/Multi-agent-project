import { Link } from 'react-router-dom'

const footerLinks = [
  { label: 'Dashboard', to: '/' },
  { label: 'Chat', to: '/chat' },
  { label: 'Docs', to: '/docs' },
]

function Footer() {
  return (
    <footer className="border-t border-(--border) bg-(--bg)">
      <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-4 py-8 md:flex-row md:justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-(--accent) text-xs font-semibold text-white">
            H
          </span>
          <span className="text-sm font-semibold text-(--text-h)">
            HR Copilot
          </span>
        </div>

        <nav className="flex items-center gap-6">
          {footerLinks.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className="text-sm text-(--text) no-underline transition-colors hover:text-(--text-h)"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <p className="m-0 text-sm text-(--text)">
          &copy; {new Date().getFullYear()} HR Copilot. All rights reserved.
        </p>
      </div>
    </footer>
  )
}

export default Footer
