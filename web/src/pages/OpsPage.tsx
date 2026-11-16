import { useQuery } from '@tanstack/react-query'
import { fetchOpsSummary } from '../api/client'

export function OpsPage() {
  const query = useQuery({
    queryKey: ['ops'],
    queryFn: ({ signal }) => fetchOpsSummary(signal),
  })

  if (query.isPending) {
    return (
      <section className="space-y-5">
        <div className="h-10 w-52 animate-pulse rounded-2xl bg-slate-800/80" />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-28 animate-pulse rounded-2xl bg-slate-800/80" />
          ))}
        </div>
      </section>
    )
  }

  if (query.isError) {
    return (
      <section className="rounded-2xl border border-red-500/40 bg-red-500/10 p-5 text-red-100">
        <h2 className="text-lg font-semibold">Unable to load operations</h2>
        <p className="mt-2">{query.error.message}</p>
        <button
          type="button"
          onClick={() => void query.refetch()}
          className="mt-4 rounded-xl border border-red-400/50 bg-red-500/10 px-3 py-2 text-sm hover:bg-red-500/20"
        >
          Retry
        </button>
      </section>
    )
  }

  const data = query.data
  const q = data.review_quality

  const statCards = [
    {
      label: 'Agreement rate',
      value: q.agreement_rate === null ? 'Not measured' : `${(q.agreement_rate * 100).toFixed(1)}%`,
      tone: 'teal',
    },
    {
      label: 'Reviewed cases',
      value: String(q.reviewed_cases),
      tone: 'sky',
    },
    {
      label: 'Pipeline runs',
      value: String(data.pipeline.length),
      tone: 'amber',
    },
    {
      label: 'Average cost / case',
      value: data.average_cost_usd === null ? 'Not measured' : `$${data.average_cost_usd.toFixed(4)}`,
      tone: 'rose',
    },
  ]

  return (
    <section className="space-y-6">
      <header className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-teal-300/90">Lead view</p>
          <h2 className="mt-2 text-3xl font-bold text-white">Operations &amp; quality</h2>
        </div>
        <p className="text-sm text-slate-400">Last 30 days • review and pipeline health</p>
      </header>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {statCards.map((card) => (
          <div key={card.label} className="rounded-2xl border border-slate-700 bg-slate-900/60 p-4 shadow-[0_16px_42px_rgba(15,23,42,0.3)]">
            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">{card.label}</p>
            <div className="mt-4 flex items-end justify-between gap-3">
              <span className="text-2xl font-semibold text-white">{card.value}</span>
              <span
                className={`inline-flex h-2.5 w-2.5 rounded-full ${
                  card.tone === 'teal'
                    ? 'bg-teal-400'
                    : card.tone === 'sky'
                      ? 'bg-sky-400'
                      : card.tone === 'amber'
                        ? 'bg-amber-400'
                        : 'bg-rose-400'
                }`}
              />
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
          <h3 className="text-lg font-semibold text-white">Agent vs human agreement</h3>
          <p className="mt-3 text-slate-300">
            {q.agreement_rate === null ? 'Not measured' : `${(q.agreement_rate * 100).toFixed(1)}%`} ({q.agreed_cases} agreed / {q.compared_cases} compared; {q.reviewed_cases} reviewed)
          </p>
        </section>

        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
          <h3 className="text-lg font-semibold text-white">Cost per case (USD)</h3>
          <p className="mt-3 text-slate-300">{data.average_cost_usd === null ? 'Not measured' : `$${data.average_cost_usd.toFixed(4)}`}</p>
          <p className="mt-2 text-sm text-slate-400">{data.cost_status}</p>
        </section>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
          <h3 className="text-lg font-semibold text-white">Pipeline runs over time</h3>
          {data.pipeline.length === 0 ? (
            <p className="mt-3 text-slate-300">No pipeline runs recorded.</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-slate-400">
                  <tr>
                    <th className="pb-2 pr-4 font-medium">Date</th>
                    <th className="pb-2 pr-4 font-medium">Rows in</th>
                    <th className="pb-2 pr-4 font-medium">Quarantined</th>
                    <th className="pb-2 font-medium">Alerts</th>
                  </tr>
                </thead>
                <tbody>
                  {data.pipeline.map((r) => (
                    <tr key={r.run_date} className="border-t border-slate-700/80 text-slate-200">
                      <td className="py-2 pr-4">{r.run_date}</td>
                      <td className="py-2 pr-4">{r.rows_in}</td>
                      <td className="py-2 pr-4">{r.rows_quarantined}</td>
                      <td className="py-2">{r.alerts_raised}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
          <h3 className="text-lg font-semibold text-white">Alerts per day</h3>
          {data.alerts_by_day.length === 0 ? (
            <p className="mt-3 text-slate-300">No alerts recorded.</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-slate-400">
                  <tr>
                    <th className="pb-2 pr-4 font-medium">Date</th>
                    <th className="pb-2 font-medium">Alerts</th>
                  </tr>
                </thead>
                <tbody>
                  {data.alerts_by_day.map((r) => (
                    <tr key={r.alert_date} className="border-t border-slate-700/80 text-slate-200">
                      <td className="py-2 pr-4">{r.alert_date}</td>
                      <td className="py-2">{r.alert_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
        <h3 className="text-lg font-semibold text-white">Latest evaluation scorecard</h3>
        <p className="mt-3 text-slate-300">{data.evaluation_status}</p>
        {data.evaluation && (
          <dl className="mt-4 space-y-3">
            {Object.entries(data.evaluation).map(([key, value]) => (
              <div key={key} className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                <dt className="text-[11px] uppercase tracking-[0.18em] text-slate-400">{key.replaceAll('_', ' ')}</dt>
                <dd className="mt-1 text-sm text-slate-200">
                  {value === null ? 'Not measured' : typeof value === 'object' ? JSON.stringify(value) : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>
    </section>
  )
}
