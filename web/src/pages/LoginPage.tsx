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
    <main className="flex min-h-screen items-center justify-center bg-slate-100 p-6">
      <form
        onSubmit={submit}
        className="w-full max-w-md space-y-5 rounded-xl bg-white p-8 shadow-sm"
      >
        <div>
          <h1 className="text-2xl font-bold">MuleWatch</h1>
          <p className="mt-1 text-sm text-slate-500">
            Sign in to the analyst console
          </p>
        </div>

        <label className="block space-y-1 text-sm">
          <span className="font-medium">Username</span>
          <input
            required
            autoComplete="username"
            value={username}
            onChange={event => setUsername(event.target.value)}
            className="w-full rounded border p-3"
          />
        </label>

        <label className="block space-y-1 text-sm">
          <span className="font-medium">Password</span>
          <input
            required
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={event => setPassword(event.target.value)}
            className="w-full rounded border p-3"
          />
        </label>

        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-blue-700 px-4 py-3 font-semibold text-white disabled:opacity-50"
        >
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
