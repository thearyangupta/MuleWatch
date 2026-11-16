import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { fetchCaseEvidence } from '../api/client'
import { DecisionForm } from '../components/DecisionForm'
import { Timeline } from '../components/Timeline'

type EvidenceItem = {
  evidence_id: string
  source: string
  summary: string
  data: unknown
}

type Finding = { claim: string; evidence_ids: string[] }
type Typology = { typology: string; explanation: string; evidence_id: string; chunk_ids: string[] }

type ValidEvidence = EvidenceItem

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((x): x is string => typeof x === 'string') : []
}

function evidenceLabel(value: string): string {
  return value.length > 18 ? `${value.slice(0, 14)}...` : value
}

function safeLink(value: string): string | null {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

function EvidenceData({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <p className="text-slate-400">No detail available.</p>
  if (typeof value !== 'object') return <p className="break-words text-slate-200">{String(value)}</p>
  if (Array.isArray(value)) {
    return (
      <ul className="list-disc space-y-1 pl-5 text-slate-200">
        {value.map((v, i) => (
          <li key={i}>
            <EvidenceData value={v} />
          </li>
        ))}
      </ul>
    )
  }

  return (
    <dl className="space-y-2">
      {Object.entries(value).map(([key, item]) => {
        const link = typeof item === 'string' && /(?:url|link|source_url)$/i.test(key) ? safeLink(item) : null

        return (
          <div key={key} className="border-b border-slate-700 pb-2 last:border-b-0">
            <dt className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">{key.replaceAll('_', ' ')}</dt>
            <dd className="mt-1 break-words text-sm text-slate-200">
              {link ? (
                <a href={link} target="_blank" rel="noopener noreferrer" className="text-teal-300 underline decoration-teal-400/60 underline-offset-2">
                  Open source
                </a>
              ) : (
                <EvidenceData value={item} />
              )}
            </dd>
          </div>
        )
      })}
    </dl>
  )
}

function Reasons({ value }: { value: unknown }) {
  const raw = Array.isArray(value)
    ? value
    : Object.entries(asObject(value)).map(([feature, score]) => ({ feature, score }))

  const parsed = raw
    .map((item) => {
      const object = asObject(item)
      const name = asString(object.feature) || asString(object.name) || asString(object.reason)
      const numeric = object.shap_value ?? object.shap ?? object.contribution ?? object.score ?? object.value
      return {
        name,
        score: typeof numeric === 'number' && Number.isFinite(numeric) ? numeric : null,
      }
    })
    .filter((item) => item.name && item.score !== null)

  if (!parsed.length) return <EvidenceData value={value} />

  const maximum = Math.max(...parsed.map((item) => Math.abs(item.score ?? 0)), 0.001)

  return (
    <div className="space-y-3">
      {parsed.map((item, i) => (
        <div key={`${item.name}-${i}`}>
          <div className="mb-1 flex justify-between gap-3 text-sm text-slate-200">
            <span>{item.name}</span>
            <span className="font-mono">{item.score?.toFixed(3)}</span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-slate-700">
            <div
              className={`h-full ${item.score! >= 0 ? 'bg-rose-400' : 'bg-sky-400'}`}
              style={{ width: `${Math.abs(item.score!) / maximum * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

function isValidEvidence(value: unknown): value is ValidEvidence {
  if (typeof value !== 'object' || value === null) return false

  const item = value as Record<string, unknown>

  return (
    typeof item.evidence_id === 'string' &&
    typeof item.source === 'string' &&
    typeof item.summary === 'string'
  )
}

export function CasePage() {
  const queryClient = useQueryClient()
  const { caseId } = useParams()
  const id = Number(caseId)
  const valid = Number.isSafeInteger(id) && id > 0
  const [selected, setSelected] = useState<string | null>(null)

  const query = useQuery({
    queryKey: ['case-evidence', id],
    queryFn: ({ signal }) => fetchCaseEvidence(id, signal),
    enabled: valid,
    staleTime: 15_000,
  })

  const report = asObject(query.data?.report)
  const findings: Finding[] = Array.isArray(report.findings)
    ? report.findings.map((item) => {
        const object = asObject(item)
        return { claim: asString(object.claim), evidence_ids: asStrings(object.evidence_ids) }
      })
    : []

  const typologies: Typology[] = Array.isArray(report.typology_matches)
    ? report.typology_matches.map((item) => {
        const object = asObject(item)
        return {
          typology: asString(object.typology),
          explanation: asString(object.explanation),
          evidence_id: asString(object.evidence_id),
          chunk_ids: asStrings(object.chunk_ids),
        }
      })
    : []

  const evidenceById = useMemo(() => {
    const map = new Map<string, EvidenceItem>()

    for (const item of query.data?.evidence ?? []) {
      const candidate = item as Partial<EvidenceItem>
      const evidenceId = typeof candidate.evidence_id === 'string' ? candidate.evidence_id : ''
      if (!evidenceId) continue
      map.set(evidenceId, {
        evidence_id: evidenceId,
        source: typeof candidate.source === 'string' ? candidate.source : 'Unknown source',
        summary: typeof candidate.summary === 'string' ? candidate.summary : 'No summary available.',
        data: candidate.data ?? null,
      })
    }

    return map
  }, [query.data?.evidence])

  const active: EvidenceItem | undefined = selected ? evidenceById.get(selected) : undefined

  const citations = (ids: string[]) =>
    ids.map((ref) => (
      <button
        key={ref}
        type="button"
        onClick={() => setSelected(ref)}
        className="rounded-lg border border-teal-500/30 bg-teal-500/10 px-2 py-1 font-mono text-[11px] text-teal-200 transition hover:border-teal-400/60 hover:bg-teal-500/15"
        aria-label={`Inspect evidence ${ref}`}
      >
        [{evidenceLabel(ref)}]
      </button>
    ))

  return (
    <section className="space-y-5">
      <Link to="/queue" className="inline-flex items-center text-sm font-medium text-teal-300 underline decoration-teal-500/50 underline-offset-4 hover:text-teal-200">
        ← Back to alert queue
      </Link>

      {!valid && <p role="alert" className="rounded-2xl border border-red-500/40 bg-red-500/10 p-4 text-red-100">Invalid case ID.</p>}

      {query.isPending && valid && (
        <div role="status" className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-2xl bg-slate-800/80" />
          ))}
          <span className="sr-only">Loading case</span>
        </div>
      )}

      {query.isError && (
        <div role="alert" className="rounded-2xl border border-red-500/40 bg-red-500/10 p-4 text-red-100">
          <span className="block">Could not load case: {query.error.message}</span>
          <button className="mt-3 rounded-xl border border-red-400/40 bg-red-500/10 px-3 py-2 text-sm hover:bg-red-500/20" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      )}

      {query.data && (
        <>
          <DecisionForm
            caseId={id}
            status={query.data.status}
            recommendedAction={asString(report.recommended_action)}
            onSuccess={async () => {
              await Promise.all([
                queryClient.invalidateQueries({ queryKey: ['case-evidence', id] }),
                queryClient.invalidateQueries({ queryKey: ['case-audit', id] }),
                queryClient.invalidateQueries({ queryKey: ['cases'] }),
              ])
            }}
          />

          <Timeline caseId={id} />

          <header className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5 shadow-[0_22px_60px_rgba(2,6,23,0.3)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Case review</p>
                <h1 className="mt-2 text-3xl font-bold text-white">Case #{query.data.case_id}</h1>
              </div>
              <span className="rounded-full bg-amber-500/15 px-3 py-1 text-sm font-semibold text-amber-200 ring-1 ring-amber-300/30">
                {query.data.status}
              </span>
            </div>

            <p className="mt-3 text-slate-300">
              Account {query.data.account_token} • Alert #{query.data.alert_id}
            </p>

            <div className="mt-5 grid gap-3 text-sm md:grid-cols-3">
              <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                <span className="block text-[11px] uppercase tracking-[0.18em] text-slate-400">Risk score</span>
                <span className="mt-2 block text-xl font-semibold text-white">{(query.data.risk_score * 100).toFixed(1)}%</span>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                <span className="block text-[11px] uppercase tracking-[0.18em] text-slate-400">Risk rating</span>
                <span className="mt-2 block text-xl font-semibold text-white">{asString(report.risk_rating) || 'Unavailable'}</span>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                <span className="block text-[11px] uppercase tracking-[0.18em] text-slate-400">Confidence</span>
                <span className="mt-2 block text-xl font-semibold text-white">
                  {typeof report.confidence === 'number' ? `${(report.confidence * 100).toFixed(0)}%` : 'Unavailable'}
                </span>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                <span className="block text-[11px] uppercase tracking-[0.18em] text-slate-400">Model</span>
                <span className="mt-2 block text-base font-medium text-slate-100">{query.data.model_version}</span>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                <span className="block text-[11px] uppercase tracking-[0.18em] text-slate-400">Prompt version</span>
                <span className="mt-2 block text-base font-medium text-slate-100">{query.data.prompt_version ?? 'Unavailable'}</span>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                <span className="block text-[11px] uppercase tracking-[0.18em] text-slate-400">Recommended action</span>
                <span className="mt-2 block text-base font-medium text-slate-100">{asString(report.recommended_action) || 'Unavailable'}</span>
              </div>
            </div>
          </header>

          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(280px,380px)]">
            <div className="space-y-5">
              <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
                <h2 className="mb-3 text-lg font-semibold text-white">Investigation summary</h2>
                <p className="whitespace-pre-wrap text-slate-200">{asString(report.summary) || 'No report summary available.'}</p>
              </section>

              <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
                <h2 className="mb-3 text-lg font-semibold text-white">Findings and citations</h2>
                {findings.length ? (
                  <ol className="space-y-4">
                    {findings.map((finding, index) => (
                      <li key={`${finding.claim}-${index}`} className="rounded-xl border border-slate-700 bg-slate-950/40 p-4">
                        <p className="text-slate-100">{finding.claim}</p>
                        <div className="mt-3 flex flex-wrap gap-2">{citations(finding.evidence_ids)}</div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-slate-300">No findings yet.</p>
                )}
              </section>

              <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
                <h2 className="mb-3 text-lg font-semibold text-white">Typology matches</h2>
                {typologies.length ? (
                  <div className="space-y-4">
                    {typologies.map((typology, index) => (
                      <article key={`${typology.typology}-${index}`} className="rounded-xl border border-slate-700 bg-slate-950/40 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <h3 className="font-semibold text-slate-100">{typology.typology || 'Unspecified typology'}</h3>
                          <button
                            type="button"
                            onClick={() => setSelected(typology.evidence_id)}
                            className="rounded-lg border border-teal-500/30 bg-teal-500/10 px-2 py-1 font-mono text-[11px] text-teal-200 hover:bg-teal-500/15"
                          >
                            [{evidenceLabel(typology.evidence_id)}]
                          </button>
                        </div>
                        <p className="mt-2 text-sm text-slate-300">{typology.explanation || 'No explanation provided.'}</p>
                        {typology.chunk_ids.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {typology.chunk_ids.map((chunk) => (
                              <span key={chunk} className="rounded-full border border-slate-600 bg-slate-800 px-2 py-1 font-mono text-[10px] text-slate-300">
                                {evidenceLabel(chunk)}
                              </span>
                            ))}
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-300">No typology matches available.</p>
                )}
              </section>
            </div>

            <aside className="space-y-5">
              <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
                <h2 className="mb-3 text-lg font-semibold text-white">Evidence inspector</h2>
                {active ? (
                  <div className="space-y-3">
                    <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                      <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Evidence ID</p>
                      <p className="mt-1 font-mono text-sm text-teal-200">{active.evidence_id}</p>
                    </div>
                    <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                      <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Source</p>
                      <p className="mt-1 text-sm text-slate-200">{active.source}</p>
                    </div>
                    <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                      <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Summary</p>
                      <p className="mt-1 text-sm text-slate-200">{active.summary}</p>
                    </div>
                    <div className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
                      <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Details</p>
                      <div className="mt-2">
                        <EvidenceData value={active.data} />
                      </div>
                    </div>
                    {active.data && isValidEvidence(active) && (
                      <button
                        type="button"
                        onClick={() => setSelected(null)}
                        className="w-full rounded-xl border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700"
                      >
                        Clear selection
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="space-y-3">
                    <p className="text-slate-300">Select an evidence citation to inspect its record.</p>
                    <div className="rounded-xl border border-dashed border-slate-600 bg-slate-950/30 p-4 text-sm text-slate-400">
                      No evidence selected.
                    </div>
                  </div>
                )}
              </section>

              <section className="rounded-2xl border border-slate-700 bg-slate-900/60 p-5">
                <h2 className="mb-3 text-lg font-semibold text-white">Feature importance</h2>
                <Reasons value={query.data.model_reasons ?? null} />
              </section>
            </aside>
          </div>
        </>
      )}
    </section>
  )
}
