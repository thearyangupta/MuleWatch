import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from 'react'
import { setApiAccessToken } from './api/client'
import { useQueryClient } from '@tanstack/react-query'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export type AuthUser = {
  username: string
  role: 'analyst' | 'lead'
}

type AuthSession = {
  token: string
  user: AuthUser
}

type AuthContextValue = {
  session: AuthSession | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

async function responseError(response: Response): Promise<Error> {
  let message = `HTTP ${response.status}`

  try {
    const body: unknown = await response.json()
    if (
      typeof body === 'object' &&
      body !== null &&
      'detail' in body &&
      typeof body.detail === 'string'
    ) {
      message = body.detail
    }
  } catch {
    // Keep the HTTP status when the response has no JSON body.
  }

  return new Error(message)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [session, setSession] = useState<AuthSession | null>(null)

  async function login(username: string, password: string) {
    const body = new URLSearchParams({ username, password })

    const tokenResponse = await fetch(`${API_BASE_URL}/auth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body,
    })

    if (!tokenResponse.ok) {
      throw await responseError(tokenResponse)
    }

    const tokenData: { access_token: string } = await tokenResponse.json()

    const userResponse = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: {
        Authorization: `Bearer ${tokenData.access_token}`,
      },
    })

    if (!userResponse.ok) {
      throw await responseError(userResponse)
    }

    const user: AuthUser = await userResponse.json()

    if (
      !user ||
      typeof user.username !== 'string' ||
      (user.role !== 'analyst' && user.role !== 'lead')
    ) {
      throw new Error('Invalid authenticated user response')
    }

    await queryClient.cancelQueries()
    queryClient.clear()
    setApiAccessToken(tokenData.access_token)
    setSession({ token: tokenData.access_token, user })
  }

  function logout() {
    setApiAccessToken(null)
    queryClient.clear()
    setSession(null)
  }

  return (
    <AuthContext.Provider value={{ session, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)

  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }

  return context
}
