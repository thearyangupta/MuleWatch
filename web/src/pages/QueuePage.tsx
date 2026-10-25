import { useQuery } from '@tanstack/react-query'
import { fetchCases } from '../api/client'

export function QueuePage() {
  const { data, isPending, isError, error } = useQuery({
    queryKey: ['cases'],
    queryFn: () => fetchCases(),
  })

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900">Case Queue</h2>
        <p className="mt-1 text-sm text-slate-500">
          Review cases awaiting analyst attention.
        </p>
      </div>

      {isPending && (
        <p role="status" className="rounded-xl bg-white p-6">
          Loading cases...
        </p>
      )}

      {isError && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-6">
          <p className="font-semibold text-red-800">Unable to load cases</p>
          <p className="mt-2 text-sm text-red-700">{error.message}</p>
        </div>
      )}

      {data && data.length === 0 && (
        <p className="rounded-xl bg-white p-6 text-slate-500">
          No cases found.
        </p>
      )}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th scope="col" className="p-4">Case ID</th>
                <th scope="col" className="p-4">Alert ID</th>
                <th scope="col" className="p-4">Status</th>
                <th scope="col" className="p-4">Summary</th>
                <th scope="col" className="p-4">Agent Action</th>
              </tr>
            </thead>
            <tbody>
              {data.slice(0, 5).map((item) => (
                <tr key={item.id} className="border-t border-slate-100">
                  <td className="p-4 font-semibold">{item.id}</td>
                  <td className="p-4">{item.alert_id}</td>
                  <td className="p-4">{item.status}</td>
                  <td className="p-4">{item.summary ?? 'Not available'}</td>
                  <td className="p-4">{item.agent_action ?? 'Pending'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
