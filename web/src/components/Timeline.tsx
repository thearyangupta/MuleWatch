import { useQuery } from '@tanstack/react-query'
import { fetchCaseAudit } from '../api/client'

export function Timeline({ caseId }: { caseId: number }) {
  const query = useQuery({
    queryKey: ['case-audit', caseId],
    queryFn: ({ signal }) => fetchCaseAudit(caseId, signal),
  })

  return (
    <section className="rounded-xl bg-white p-5">
      <h2 className="mb-3 text-lg font-semibold">Audit timeline</h2>

      {query.isPending && <p role="status">Loading audit history...</p>}

      {query.isError && (
        <p role="alert" className="text-red-700">
          Could not load audit history: {query.error.message}
        </p>
      )}

      {query.data && (
        <>
          {!query.data.chain_valid && (
            <p role="alert" className="mb-4 rounded bg-red-50 p-3 text-red-700">
              Audit-chain verification failed. Review the integrity warning.
            </p>
          )}

          {!query.data.events.length ? (
            <p>No audit events recorded for this case.</p>
          ) : (
            <ol className="space-y-4 border-l-2 border-slate-200 pl-5">
              {query.data.events.map(event => (
                <li key={event.id} className="relative">
                  <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full bg-blue-600" />

                  <h3 className="font-semibold">
                    {event.action.replaceAll('_', ' ')}
                  </h3>

                  <p className="text-sm text-slate-600">
                    Actor: {event.actor}
                  </p>

                  <time
                    dateTime={event.created_at}
                    className="text-xs text-slate-500"
                  >
                    {new Date(event.created_at).toLocaleString()}
                  </time>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  )
}
