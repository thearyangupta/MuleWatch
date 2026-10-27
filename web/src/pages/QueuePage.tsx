import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router'
import { investigateAlert, type CaseFilters } from '../api/client'
import { useAlertStatus, useCases } from '../hooks/useCases'

const FINAL = new Set(['AWAITING_REVIEW', 'CLOSED', 'ESCALATED',
  'NEEDS_MANUAL_REVIEW', 'INSUFFICIENT_EVIDENCE', 'COMPLETE'])
const riskClass: Record<string, string> = {
  LOW: 'bg-green-100 text-green-900',
  MEDIUM: 'bg-amber-100 text-amber-900',
  HIGH: 'bg-red-100 text-red-900',
}
function age(iso: string): string {
  const ms = Math.max(0, Date.now() - new Date(iso).getTime())
  const hours = Math.floor(ms / 3_600_000)
  return hours < 1 ? `${Math.floor(ms / 60_000)}m` : hours < 24 ? `${hours}h` : `${Math.floor(hours / 24)}d`
}
function token(id: string): string { return `****${id.slice(-4)}` }

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
  return (
    <section className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold text-slate-900">Alert Queue</h2>
        <p className="mt-1 text-sm text-slate-500">Review and investigate flagged accounts.</p>
      </header>
      <div className="grid gap-3 rounded-xl bg-white p-4 md:grid-cols-5">
        <label className="text-sm">Status
          <select aria-label="Status" className="mt-1 w-full rounded border p-2" value={filters.status ?? ''} onChange={e => setFilter('status', e.target.value)}>
            <option value="">All statuses</option>
            {['NEW','OPEN','INVESTIGATING','AWAITING_REVIEW','CLOSED','ESCALATED','NEEDS_MANUAL_REVIEW','INSUFFICIENT_EVIDENCE','COMPLETE'].map(s => <option key={s} value={s}>{s.replaceAll('_',' ')}</option>)}
          </select>
        </label>
        <label className="text-sm">Risk
          <select aria-label="Risk" className="mt-1 w-full rounded border p-2" value={filters.risk ?? ''} onChange={e => setFilter('risk', e.target.value)}>
            <option value="">All risks</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option><option value="LOW">Low</option>
          </select>
        </label>
        <label className="text-sm">From date
          <input aria-label="From date" type="date" className="mt-1 w-full rounded border p-2" value={filters.dateFrom ?? ''} onChange={e => setFilter('date_from', e.target.value)} />
        </label>
        <label className="text-sm">To date
          <input aria-label="To date" type="date" className="mt-1 w-full rounded border p-2" value={filters.dateTo ?? ''} onChange={e => setFilter('date_to', e.target.value)} />
        </label>
        <label className="text-sm">Sort
          <select aria-label="Sort" className="mt-1 w-full rounded border p-2" value={filters.sort} onChange={e => setFilter('sort', e.target.value)}>
            <option value="newest">Newest first</option><option value="oldest">Oldest first</option>
          </select>
        </label>
      </div>
      {message && <p role="status" className="rounded bg-blue-50 p-3 text-blue-900">{message}</p>}
      {status.isError && <p role="alert" className="rounded bg-red-50 p-3 text-red-800">Polling failed: {status.error.message}</p>}
      {queue.isPending && <div role="status" aria-label="Loading alerts" className="space-y-3">{Array.from({length: 5}, (_, i) => <div key={i} className="h-14 animate-pulse rounded bg-slate-200" />)}<span className="sr-only">Loading alerts</span></div>}
      {queue.isError && <div role="alert" className="rounded border border-red-200 bg-red-50 p-5"><strong>Unable to load alerts</strong><p>{queue.error.message}</p><button className="mt-3 rounded bg-red-700 px-3 py-2 text-white" onClick={() => void queue.refetch()}>Retry</button></div>}
      {queue.data && queue.data.items.length === 0 && <p className="rounded bg-white p-6">No alerts match your filters.</p>}
      {queue.data && queue.data.items.length > 0 && <div className="overflow-x-auto rounded border bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-600"><tr>{['Alert Date','Account Token','Model Score','Risk','Status','Agent Action','Age','Action'].map(h => <th key={h} scope="col" className="p-3">{h}</th>)}</tr></thead>
          <tbody>{queue.data.items.map(item => <tr key={item.alert_id} className="border-t hover:bg-slate-50">
            <td className="p-3">{item.alert_date}</td>
            <td className="p-3 font-mono">{token(item.account_id)}</td>
            <td className="p-3">{(item.risk_score * 100).toFixed(1)}%</td>
            <td className="p-3"><span className={`rounded-full px-2 py-1 text-xs font-semibold ${riskClass[item.risk] ?? 'bg-slate-100 text-slate-800'}`}>{item.risk}</span></td>
            <td className="p-3">{activeId === item.alert_id ? 'INVESTIGATING' : item.status}</td>
            <td className="p-3">{item.agent_action ?? 'Pending'}</td>
            <td className="p-3">{age(item.created_at)}</td>
            <td className="p-3">{item.status === 'NEW' ? <button type="button" className="rounded bg-blue-700 px-3 py-2 text-white disabled:opacity-50" disabled={activeId !== null} onClick={() => start(item.alert_id, new Date().getTime())}>{activeId === item.alert_id ? 'Investigatingâ€¦' : 'Investigate'}</button> : item.id !== null ? <button type="button" className="rounded border px-3 py-2" onClick={() => navigate(`/cases/${item.id}`)}>Open case</button> : <span>â€”</span>}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      {queue.data && <footer className="flex items-center justify-between gap-3 text-sm"><span>{queue.data.total} alerts Â· Page {queue.data.page} of {Math.max(1, queue.data.total_pages)}</span><div className="flex gap-2"><button type="button" className="rounded border px-3 py-2 disabled:opacity-40" disabled={filters.page <= 1} onClick={() => changePage(filters.page - 1)}>Previous</button><button type="button" className="rounded border px-3 py-2 disabled:opacity-40" disabled={filters.page >= queue.data.total_pages} onClick={() => changePage(filters.page + 1)}>Next</button></div></footer>}
    </section>
  )
}
