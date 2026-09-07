import { NavLink } from 'react-router-dom'

const links = [
  { to: '/', label: '仪表盘' },
  { to: '/write', label: '写作练习' },
  { to: '/speaking', label: '口语练习' },
  { to: '/listening', label: '听力' },
  { to: '/vocab', label: '词汇' },
  { to: '/skills', label: '能力树' },
  { to: '/mock', label: '模考' },
  { to: '/history', label: '历史记录' },
]

export function NavBar() {
  return (
    <nav className="flex items-center gap-6 border-b border-slate-200 bg-white px-6 py-3">
      <span className="text-lg font-bold text-indigo-600">雅思私教</span>
      {links.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          className={({ isActive }) =>
            isActive ? 'font-semibold text-indigo-600' : 'text-slate-500 hover:text-slate-800'
          }
        >
          {l.label}
        </NavLink>
      ))}
    </nav>
  )
}
