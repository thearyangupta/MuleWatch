import { useState, type FormEvent } from 'react'
import { useAuth } from '../auth'

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      await login(username, password)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(20,184,166,0.18),_transparent_30%),linear-gradient(180deg,#020817_0%,#0b1220_100%)] p-6">
      <form
        onSubmit={submit}
        className="w-full max-w-md rounded-3xl border border-slate-700 bg-slate-900/80 p-8 shadow-[0_24px_80px_rgba(2,6,23,0.7)] backdrop-blur-sm"
      >
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-500/15 text-xl font-bold text-teal-200 ring-1 ring-teal-400/30">
            M
          </div>
          <div>
            <h1 className="text-2xl font-bold text-white">MuleWatch</h1>
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Analyst Console</p>
          </div>
        </div>

        <div className="space-y-5">
          <label className="block space-y-2 text-sm">
            <span className="font-medium text-slate-200">Username</span>
            <input
              required
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              className="w-full rounded-xl border border-slate-600 bg-slate-950/80 p-3 text-slate-100 placeholder:text-slate-500 focus:border-teal-400 focus:outline-none"
              placeholder="analyst"
            />
          </label>

          <label className="block space-y-2 text-sm">
            <span className="font-medium text-slate-200">Password</span>
            <input
              required
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="w-full rounded-xl border border-slate-600 bg-slate-950/80 p-3 text-slate-100 placeholder:text-slate-500 focus:border-teal-400 focus:outline-none"
              placeholder="••••••••"
            />
          </label>

          {error && (
            <p role="alert" className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-100">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-teal-500 px-4 py-3 font-semibold text-slate-950 transition hover:bg-teal-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? 'Signing in...' : 'Sign in'}
          </button>
        </div>
      </form>
    </main>
  )
}
