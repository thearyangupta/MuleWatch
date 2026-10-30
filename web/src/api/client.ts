import type { operations } from './types'

export type CaseListResponse =
  operations['list_cases_cases_get']['responses'][200]['content']['application/json']
export type CaseListItem = CaseListResponse['items'][number]
export type InvestigationResponse =
  operations['investigate_alert_investigate__alert_id__post']['responses'][200]['content']['application/json']
export type AlertStatusResponse =
  operations['get_alert_investigation_status_cases_alerts__alert_id__status_get']['responses'][200]['content']['application/json']

export type CaseFilters = {
  status?: string
  risk?: 'LOW' | 'MEDIUM' | 'HIGH'
  dateFrom?: string
  dateTo?: string
  page: number
  pageSize: number
  sort: 'newest' | 'oldest'
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

function urlFor(path: string): URL {
  return new URL(`${API_BASE_URL.replace(/\/$/, '')}${path}`, window.location.origin)
}

async function checkResponse(response: Response): Promise<void> {
  if (response.ok) return
  let detail = `HTTP ${response.status}`
  try {
    const value: unknown = await response.json()
    if (typeof value === 'object' && value !== null && 'detail' in value && typeof value.detail === 'string') {
      detail = value.detail
    }
  } catch { /* HTTP code remains available */ }
  throw new Error(detail)
}

export async function fetchCases(filters: CaseFilters, signal?: AbortSignal): Promise<CaseListResponse> {
  const url = urlFor('/cases')
  if (filters.status) url.searchParams.set('status', filters.status)
  if (filters.risk) url.searchParams.set('risk', filters.risk)
  if (filters.dateFrom) url.searchParams.set('date_from', filters.dateFrom)
  if (filters.dateTo) url.searchParams.set('date_to', filters.dateTo)
  url.searchParams.set('page', String(filters.page))
  url.searchParams.set('page_size', String(filters.pageSize))
  url.searchParams.set('sort', filters.sort)
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  await checkResponse(response)
  const value: unknown = await response.json()
  if (typeof value !== 'object' || value === null || !('items' in value) || !Array.isArray(value.items)) {
    throw new Error('Unexpected queue response')
  }
  return value as CaseListResponse
}

export async function investigateAlert(alertId: number): Promise<InvestigationResponse> {
  const response = await fetch(urlFor(`/investigate/${alertId}`), {
    method: 'POST', headers: { Accept: 'application/json' },
  })
  await checkResponse(response)
  return (await response.json()) as InvestigationResponse
}

export async function fetchAlertStatus(alertId: number, signal?: AbortSignal): Promise<AlertStatusResponse> {
  const response = await fetch(urlFor(`/cases/alerts/${alertId}/status`), {
    signal, headers: { Accept: 'application/json' },
  })
  await checkResponse(response)
  return (await response.json()) as AlertStatusResponse
}

export type CaseEvidenceDetail =
  operations['get_case_evidence_cases__case_id__evidence_get']['responses'][200]['content']['application/json']

export async function fetchCaseEvidence(caseId: number, signal?: AbortSignal): Promise<CaseEvidenceDetail> {
  const response = await fetch(urlFor(`/cases/${caseId}/evidence`), {
    signal, headers: { Accept: 'application/json' },
  })
  await checkResponse(response)
  return (await response.json()) as CaseEvidenceDetail
}
