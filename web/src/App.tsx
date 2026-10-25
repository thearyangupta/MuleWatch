import { NavLink, Navigate, Route, Routes } from 'react-router'
import { QueuePage } from './pages/QueuePage'
import { OpsPage } from './pages/OpsPage'

const navigation = [
  { to: '/queue', label: 'Queue' },
  { to: '/ops', label: 'Ops' },
]

function App() {
  return (
    <div className="min-h-screen md:flex">
      <aside className="bg-slate-900 p-6 text-white md:min-h-screen md:w-64">
        <h1 className="text-2xl font-bold">MuleWatch</h1>
        <p className="mt-1 text-xs text-slate-400">Analyst Console</p>

        <nav aria-label="Main navigation" className="mt-8 space-y-2">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `block rounded-lg px-4 py-3 text-sm ${
                  isActive
                    ? 'bg-blue-600 font-semibold text-white'
                    : 'text-slate-300 hover:bg-slate-800'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="border-b border-slate-200 bg-white px-6 py-5">
          <p className="font-semibold text-slate-900">
            MuleWatch Analyst Console
          </p>
          <p className="text-xs text-slate-500">
            Investigation and review workspace
          </p>
        </header>

        <main className="mx-auto max-w-6xl p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/queue" replace />} />
            <Route path="/queue" element={<QueuePage />} />
            <Route path="/ops" element={<OpsPage />} />
            <Route path="*" element={<Navigate to="/queue" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default App
