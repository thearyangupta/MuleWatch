import { useQuery } from '@tanstack/react-query'
import { fetchOpsSummary } from '../api/client'

export function OpsPage() {
  const query = useQuery({ queryKey: ['ops'], queryFn: ({ signal }) => fetchOpsSummary(signal) })
  if (query.isPending) return <p role="status">Loading operations...</p>
  if (query.isError) return <p role="alert">Unable to load operations: {query.error.message} <button onClick={() => void query.refetch()}>Retry</button></p>
  const data = query.data
  const q = data.review_quality
  return <section className="space-y-6">
    <h2 className="text-2xl font-bold">Operations &amp; quality</h2>
    <p>Lead-only ?? last 30 days</p>
    <div className="rounded-xl bg-white p-5"><h3 className="font-semibold">Agent vs human agreement</h3>
      <p>{q.agreement_rate === null ? 'Not measured' : `${(q.agreement_rate * 100).toFixed(1)}%`} ({q.agreed_cases} agreed / {q.compared_cases} compared; {q.reviewed_cases} reviewed)</p></div>
    <div className="rounded-xl bg-white p-5"><h3 className="font-semibold">Pipeline runs over time</h3>
      {data.pipeline.length === 0 ? <p>No pipeline runs recorded.</p> : <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>Date</th><th>Rows in</th><th>Quarantined</th><th>Alerts raised</th></tr></thead><tbody>
      {data.pipeline.map(r => <tr className="border-t" key={r.run_date}><td>{r.run_date}</td><td>{r.rows_in}</td><td>{r.rows_quarantined}</td><td>{r.alerts_raised}</td></tr>)}
      </tbody></table></div>}</div>
    <div className="rounded-xl bg-white p-5"><h3 className="font-semibold">Alerts per day</h3>
      {data.alerts_by_day.length === 0 ? <p>No alerts recorded.</p> : <div className="overflow-x-auto"><table className="w-full text-left"><thead><tr><th>Date</th><th>Alerts</th></tr></thead><tbody>
      {data.alerts_by_day.map(r => <tr className="border-t" key={r.alert_date}><td>{r.alert_date}</td><td>{r.alert_count}</td></tr>)}
      </tbody></table></div>}</div>
    <div className="rounded-xl bg-white p-5"><h3 className="font-semibold">Latest Week 5 evaluation scorecard</h3><p>{data.evaluation_status}</p>
      {data.evaluation && <dl>{Object.entries(data.evaluation).map(([key,value]) => <div key={key} className="mt-2"><dt className="font-medium">{key.replaceAll('_',' ')}</dt><dd>{value === null ? 'Not measured' : typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>}</div>
    <div className="rounded-xl bg-white p-5"><h3 className="font-semibold">Cost per case (USD)</h3>
      <p>{data.average_cost_usd === null ? 'Not measured' : `$${data.average_cost_usd.toFixed(4)}`}</p><p>{data.cost_status}</p></div>
  </section>
}
