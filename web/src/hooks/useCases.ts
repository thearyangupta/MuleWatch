import { useQuery } from '@tanstack/react-query'
import { fetchAlertStatus, fetchCases, type CaseFilters } from '../api/client'

export function useCases(filters: CaseFilters) {
  return useQuery({
    queryKey: ['cases', filters.status ?? '', filters.risk ?? '', filters.dateFrom ?? '',
      filters.dateTo ?? '', filters.page, filters.pageSize, filters.sort],
    queryFn: ({ signal }) => fetchCases(filters, signal),
    staleTime: 15_000,
  })
}

export function useAlertStatus(alertId: number | null, polling: boolean) {
  return useQuery({
    queryKey: ['alert-status', alertId],
    queryFn: ({ signal }) => fetchAlertStatus(alertId!, signal),
    enabled: alertId !== null && polling,
    refetchInterval: polling ? 2_000 : false,
    staleTime: 0,
  })
}
