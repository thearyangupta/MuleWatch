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
    <div className="min-h-screen bg-slate-950 text-slate-100 md:flex">
      <aside className="border-b border-slate-800 bg-slate-950/90 p-6 md:min-h-screen md:w-72 md:border-b-0 md:border-r">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-500/15 text-lg font-bold text-teal-200 ring-1 ring-teal-400/30">
            M
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">MuleWatch</h1>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Analyst Console</p>
          </div>
        </div>

        <nav aria-label="Main navigation" className="mt-8 space-y-2">
          {navigation
            .filter((item) => item.to !== '/ops' || session.user.role === 'lead')
            .map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block rounded-xl px-4 py-3 text-sm font-medium transition ${
                    isActive
                      ? 'bg-teal-500/15 text-teal-100 ring-1 ring-teal-400/30'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
        </nav>
      </aside>

      <div className="min-w-0 flex-1 bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.15),_transparent_35%),linear-gradient(180deg,#020817_0%,#0b1220_100%)]">
        <div className="flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-950/60 px-6 py-3 text-sm text-slate-300 backdrop-blur-sm">
          <div className="hidden text-xs uppercase tracking-[0.2em] text-slate-500 sm:block">Investigation workspace</div>
          <div className="ml-auto flex items-center gap-3">
            <span className="rounded-full border border-slate-700 bg-slate-900/60 px-2.5 py-1 text-slate-200">
              {session.user.username} <span className="text-slate-400">({session.user.role})</span>
            </span>
            <button type="button" onClick={logout} className="rounded-xl border border-slate-700 bg-slate-900/60 px-3 py-2 text-slate-200 transition hover:border-slate-500 hover:text-white">
              Log out
            </button>
          </div>
        </div>

        <header className="border-b border-slate-800 px-6 py-5">
          <p className="text-xs uppercase tracking-[0.18em] text-teal-300/90">Monitoring</p>
          <p className="mt-2 text-2xl font-semibold text-white">MuleWatch Analyst Console</p>
          <p className="mt-1 text-sm text-slate-400">Investigation and review workspace</p>
        </header>

        <main className="mx-auto max-w-7xl p-4 md:p-7">
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
