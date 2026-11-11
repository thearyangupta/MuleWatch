import { useAuth } from './auth'
import { LoginPage } from './pages/LoginPage'
import { CasePage } from './pages/CasePage'
import { NavLink, Navigate, Route, Routes } from 'react-router'
import { QueuePage } from './pages/QueuePage'
import { OpsPage } from './pages/OpsPage'

const navigation = [
  { to: '/queue', label: 'Queue' },
  { to: '/ops', label: 'Ops' },
]

function App() {
  const { session, logout } = useAuth()

  if (!session) {
    return <LoginPage />
  }

  return (
    <div className="mw-app min-h-screen md:flex">
      <aside className="mw-sidebar p-6 text-white md:min-h-screen md:w-64">
        <h1 className="mw-brand text-2xl font-bold">MuleWatch</h1>
        <p className="mt-1 text-xs text-slate-400">Analyst Console</p>

        <nav aria-label="Main navigation" className="mt-8 space-y-2">
          {navigation.filter(item => item.to !== '/ops' || session.user.role === 'lead').map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block rounded-lg px-4 py-3 text-sm ${
                  isActive
                    ? 'mw-nav-active font-semibold text-white'
                    : 'mw-nav-idle'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="mw-workspace min-w-0 flex-1">
        <div className="mw-topbar flex items-center justify-end gap-3 border-b px-6 py-3 text-sm">
          <span>{session.user.username} ({session.user.role})</span>
          <button type="button" onClick={logout} className="text-blue-700 underline">
            Log out
          </button>
        </div>
        <header className="mw-pageheader border-b px-6 py-5">
          <p className="font-semibold text-slate-900">
            MuleWatch Analyst Console
          </p>
          <p className="text-xs text-slate-500">
            Investigation and review workspace
          </p>
        </header>

        <main className="mw-content mx-auto max-w-7xl p-4 md:p-7">
          <Routes>
            <Route path="/" element={<Navigate to="/queue" replace />} />
            <Route path="/queue" element={<QueuePage />} />
            <Route path="/cases/:caseId" element={<CasePage />} />
            <Route path="/ops" element={session.user.role === 'lead' ? <OpsPage /> : <Navigate to="/queue" replace />} />
            <Route path="*" element={<Navigate to="/queue" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default App
