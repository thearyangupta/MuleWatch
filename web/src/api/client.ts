import type { operations } from './types'

export type CaseListResponse =
  operations['list_cases_cases_get']['responses'][200]['content']['application/json']

export type CaseListItem = CaseListResponse[number]

export type CaseStatus =
  NonNullable<operations['list_cases_cases_get']['parameters']['query']>['status']

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

export async function fetchCases(
  status?: CaseStatus,
): Promise<CaseListResponse> {
  const url = new URL(
    `${API_BASE_URL.replace(/\/$/, '')}/cases`,
    window.location.origin,
  )

  if (status) {
    url.searchParams.set('status', status)
  }

  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Unable to load cases (HTTP ${response.status})`)
  }

  const data: unknown = await response.json()

  if (!Array.isArray(data)) {
    throw new Error('Unexpected case-list response')
  }

  return data as CaseListResponse
}
