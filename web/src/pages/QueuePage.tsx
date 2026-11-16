import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router'
import { investigateAlert, type CaseFilters } from '../api/client'
import { useAlertStatus, useCases } from '../hooks/useCases'

const FINAL = new Set([
  'AWAITING_REVIEW',
  'CLOSED',
  'ESCALATED',
  'NEEDS_MANUAL_REVIEW',
  'INSUFFICIENT_EVIDENCE',
  'COMPLETE',
])

const riskClass: Record<string, string> = {
  LOW: 'bg-emerald-500/15 text-emerald-200 ring-1 ring-emerald-400/30',
  MEDIUM: 'bg-amber-500/15 text-amber-200 ring-1 ring-amber-400/30',
  HIGH: 'bg-rose-500/15 text-rose-200 ring-1 ring-rose-400/30',
}

function age(iso: string): string {
  const ms = Math.max(0, Date.now() - new Date(iso).getTime())
  const hours = Math.floor(ms / 3_600_000)
  return hours < 1 ? `${Math.floor(ms / 60_000)}m` : hours < 24 ? `${hours}h` : `${Math.floor(hours / 24)}d`
}

function token(id: string): string {
  return `****${id.slice(-4)}`
}

export function QueuePage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const [activeId, setActiveId] = useState<number | null>(null)
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [message, setMessage] = useState('')
  const [polling, setPolling] = useState(false)

  const pageParam = Number(params.get('page'))
  const filters: CaseFilters = {
    status: params.get('status') || undefined,
    risk: (params.get('risk') || undefined) as CaseFilters['risk'],
    dateFrom: params.get('date_from') || undefined,
    dateTo: params.get('date_to') || undefined,
    page: Number.isSafeInteger(pageParam) && pageParam > 0 ? pageParam : 1,
    pageSize: 20,
    sort: params.get('sort') === 'oldest' ? 'oldest' : 'newest',
  }

  const queue = useCases(filters)
  const status = useAlertStatus(activeId, polling)
  const investigate = useMutation({
    mutationFn: investigateAlert,
    onSuccess: (result) => {
      setMessage(`Investigation returned ${result.status}`)
      void qc.invalidateQueries({ queryKey: ['cases'] })
      if (FINAL.has(result.status)) {
        setPolling(false)
        setActiveId(null)
        setStartedAt(null)
      } else {
        setPolling(true)
      }
    },
    onError: (error) => {
      setMessage(`Investigation failed: ${error.message}`)
      setPolling(false)
      setActiveId(null)
      setStartedAt(null)
    },
  })

  useEffect(() => {
    if (!polling || activeId === null || !status.data) return
    if (!FINAL.has(status.data.status)) return

    const timer = window.setTimeout(() => {
      setMessage(`Alert ${activeId} reached ${status.data.status}`)
      setPolling(false)
      setActiveId(null)
      setStartedAt(null)
      void qc.invalidateQueries({ queryKey: ['cases'] })
    }, 0)

    return () => window.clearTimeout(timer)
  }, [activeId, polling, qc, status.data])

  useEffect(() => {
    if (!polling || startedAt === null) return
    const timer = window.setTimeout(() => {
      setMessage('Polling timed out after 60 seconds. Refresh to check the investigation.')
      setPolling(false)
      setActiveId(null)
      setStartedAt(null)
    }, Math.max(0, 60_000 - (Date.now() - startedAt)))
    return () => window.clearTimeout(timer)
  }, [polling, startedAt])

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    next.set('page', '1')
    setParams(next)
  }

  function changePage(page: number) {
    const next = new URLSearchParams(params)
    next.set('page', String(page))
    setParams(next)
  }

  function start(alertId: number, startedAtMs: number) {
    if (activeId !== null) return
    setMessage('')
    setActiveId(alertId)
    setStartedAt(startedAtMs)
    setPolling(false)
    investigate.mutate(alertId)
  }

  const summary = queue.data
    ? {
        total: queue.data.total,
        highRisk: queue.data.items.filter((item) => item.risk === 'HIGH').length,
        awaitingReview: queue.data.items.filter((item) => item.status === 'AWAITING_REVIEW').length,
        investigating: queue.data.items.filter((item) => item.status === 'INVESTIGATING').length,
      }
    : { total: 0, highRisk: 0, awaitingReview: 0, investigating: 0 }

  const metricCards = [
    { label: 'Total alerts', value: String(summary.total), tone: 'emerald' },
    { label: 'High risk', value: String(summary.highRisk), tone: 'rose' },
    { label: 'Awaiting review', value: String(summary.awaitingReview), tone: 'amber' },
    { label: 'Investigating', value: String(summary.investigating), tone: 'sky' },
  ]

  return (
    <section className="space-y-6">
      <header className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-300/90">Operations dashboard</p>
          <h2 className="mt-2 text-3xl font-bold text-slate-50">Alert Queue</h2>
        </div>
        <p className="text-sm text-slate-400">Review and investigate flagged accounts.</p>
      </header>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {metricCards.map((card) => (
          <div key={card.label} className="rounded-2xl border border-slate-700 bg-slate-900/60 p-4 shadow-[0_16px_42px_rgba(15,23,42,0.3)]">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">{card.label}</p>
            <div className="mt-4 flex items-end justify-between gap-3">
              <span className="text-3xl font-semibold text-white">{card.value}</span>
              <span className={`inline-flex h-2.5 w-2.5 rounded-full ${card.tone === 'emerald' ? 'bg-emerald-400' : card.tone === 'rose' ? 'bg-rose-400' : card.tone === 'amber' ? 'bg-amber-400' : 'bg-sky-400'}`} />
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-3 rounded-2xl border border-slate-700 bg-slate-900/60 p-4 md:grid-cols-5">
        <label className="text-sm text-slate-300">
          <span className="mb-1 block text-xs uppercase tracking-[0.15em] text-slate-400">Status</span>
          <select aria-label="Status" className="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950/60 p-2.5 text-slate-100" value={filters.status ?? ''} onChange={e => setFilter('status', e.target.value)}>
            <option value="">All statuses</option>
            {['NEW', 'OPEN', 'INVESTIGATING', 'AWAITING_REVIEW', 'CLOSED', 'ESCALATED', 'NEEDS_MANUAL_REVIEW', 'INSUFFICIENT_EVIDENCE', 'COMPLETE'].map((s) => (
              <option key={s} value={s}>{s.replaceAll('_', ' ')}</option>
            ))}
          </select>
        </label>

        <label className="text-sm text-slate-300">
          <span className="mb-1 block text-xs uppercase tracking-[0.15em] text-slate-400">Risk</span>
          <select aria-label="Risk" className="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950/60 p-2.5 text-slate-100" value={filters.risk ?? ''} onChange={e => setFilter('risk', e.target.value)}>
            <option value="">All risks</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>
        </label>

        <label className="text-sm text-slate-300">
          <span className="mb-1 block text-xs uppercase tracking-[0.15em] text-slate-400">From date</span>
          <input aria-label="From date" type="date" className="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950/60 p-2.5 text-slate-100" value={filters.dateFrom ?? ''} onChange={e => setFilter('date_from', e.target.value)} />
        </label>

        <label className="text-sm text-slate-300">
          <span className="mb-1 block text-xs uppercase tracking-[0.15em] text-slate-400">To date</span>
          <input aria-label="To date" type="date" className="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950/60 p-2.5 text-slate-100" value={filters.dateTo ?? ''} onChange={e => setFilter('date_to', e.target.value)} />
        </label>

        <label className="text-sm text-slate-300">
          <span className="mb-1 block text-xs uppercase tracking-[0.15em] text-slate-400">Sort</span>
          <select aria-label="Sort" className="mt-1 w-full rounded-xl border border-slate-600 bg-slate-950/60 p-2.5 text-slate-100" value={filters.sort} onChange={e => setFilter('sort', e.target.value)}>
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
          </select>
        </label>
      </div>

      {message && <p role="status" className="rounded-2xl border border-teal-600/30 bg-teal-500/10 p-3 text-sm text-teal-100">{message}</p>}
      {status.isError && <p role="alert" className="rounded-2xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-100">Polling failed: {status.error.message}</p>}
      {queue.isPending && (
        <div role="status" aria-label="Loading alerts" className="space-y-3">
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-2xl bg-slate-800/80" />
          ))}
          <span className="sr-only">Loading alerts</span>
        </div>
      )}
      {queue.isError && (
        <div role="alert" className="rounded-2xl border border-red-500/40 bg-red-500/10 p-5">
          <strong className="block text-lg text-red-50">Unable to load alerts</strong>
          <p className="mt-2 text-red-100">{queue.error.message}</p>
          <button className="mt-4 rounded-xl bg-red-500 px-3 py-2 text-white hover:bg-red-400" onClick={() => void queue.refetch()}>
            Retry
          </button>
        </div>
      )}
      {queue.data && queue.data.items.length === 0 && <p className="rounded-2xl border border-slate-700 bg-slate-900/60 p-6 text-slate-300">No alerts match your filters.</p>}

      {queue.data && queue.data.items.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-900/60 shadow-[0_20px_60px_rgba(2,6,23,0.42)]">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-800/90 text-slate-300">
                <tr>
                  {['Alert Date', 'Account Token', 'Model Score', 'Risk', 'Status', 'Agent Action', 'Age', 'Action'].map((heading) => (
                    <th key={heading} scope="col" className="p-3 text-xs font-medium uppercase tracking-[0.14em] text-slate-400">
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {queue.data.items.map((item) => (
                  <tr key={item.alert_id} className="border-t border-slate-700/80 transition-colors hover:bg-slate-800/60">
                    <td className="p-3 text-slate-200">{item.alert_date}</td>
                    <td className="p-3 font-mono text-slate-100">{token(item.account_id)}</td>
                    <td className="p-3 text-slate-200">{(item.risk_score * 100).toFixed(1)}%</td>
                    <td className="p-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${riskClass[item.risk] ?? 'bg-slate-700 text-slate-100'}`}>
                        {item.risk}
                      </span>
                    </td>
                    <td className="p-3 text-slate-200">{activeId === item.alert_id ? 'INVESTIGATING' : item.status}</td>
                    <td className="p-3 text-slate-200">{item.agent_action ?? 'Pending'}</td>
                    <td className="p-3 text-slate-200">{age(item.created_at)}</td>
                    <td className="p-3">
                      {item.status === 'NEW' ? (
                        <button
                          type="button"
                          className="rounded-xl bg-teal-500 px-3 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-teal-500/20 transition hover:bg-teal-400 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={activeId !== null}
                          onClick={() => start(item.alert_id, new Date().getTime())}
                        >
                          {activeId === item.alert_id ? 'Investigating...' : 'Investigate'}
                        </button>
                      ) : item.id !== null ? (
                        <button
                          type="button"
                          className="rounded-xl border border-slate-600 bg-slate-800 px-3 py-2 text-sm font-medium text-slate-100 transition hover:border-slate-400 hover:bg-slate-700"
                          onClick={() => navigate(`/cases/${item.id}`)}
                        >
                          Open case
                        </button>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {queue.data && (
        <footer className="flex flex-col gap-3 text-sm text-slate-300 sm:flex-row sm:items-center sm:justify-between">
          <span>
            {queue.data.total} alerts · Page {queue.data.page} of {Math.max(1, queue.data.total_pages)}
          </span>
          <div className="flex gap-2">
            <button type="button" className="rounded-xl border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 transition hover:border-slate-400 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40" disabled={filters.page <= 1} onClick={() => changePage(filters.page - 1)}>
              Previous
            </button>
            <button type="button" className="rounded-xl border border-slate-600 bg-slate-900 px-3 py-2 text-slate-100 transition hover:border-slate-400 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40" disabled={filters.page >= queue.data.total_pages} onClick={() => changePage(filters.page + 1)}>
              Next
            </button>
          </div>
        </footer>
      )}
    </section>
  )
}
