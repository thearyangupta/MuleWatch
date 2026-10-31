import { DecisionForm } from '../components/DecisionForm'
import { Timeline } from '../components/Timeline'

type ValidEvidence = {
  evidence_id: string
  source: string
  summary: string
  data: unknown
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
import { useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { fetchCaseEvidence, type CaseEvidenceDetail } from '../api/client'

type Evidence = CaseEvidenceDetail['evidence'][number]
type Finding = { claim: string; evidence_ids: string[] }
type Typology = { typology: string; explanation: string; evidence_id: string; chunk_ids: string[] }

function asObject(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : {}
}
function asString(value: unknown): string { return typeof value === 'string' ? value : '' }
function asStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((x): x is string => typeof x === 'string') : []
}
function evidenceLabel(value: string): string { return value.length > 18 ? `${value.slice(0, 14)}...` : value }
function safeLink(value: string): string | null {
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : null } catch { return null }
}
function EvidenceData({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <p className="text-slate-500">No detail available.</p>
  if (typeof value !== 'object') return <p className="break-words">{String(value)}</p>
  if (Array.isArray(value)) return <ul className="list-disc space-y-1 pl-5">{value.map((v, i) => <li key={i}><EvidenceData value={v} /></li>)}</ul>
  return <dl className="space-y-2">{Object.entries(value).map(([key, item]) => {
    const link = typeof item === 'string' && /(?:url|link|source_url)$/i.test(key) ? safeLink(item) : null
    return <div key={key} className="border-b pb-2"><dt className="text-xs font-semibold uppercase text-slate-500">{key.replaceAll('_', ' ')}</dt><dd className="mt-1 break-words text-sm">{link ? <a href={link} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline">Open source</a> : <EvidenceData value={item} />}</dd></div>
  })}</dl>
}
function Reasons({ value }: { value: unknown }) {
  const raw = Array.isArray(value) ? value : Object.entries(asObject(value)).map(([feature, score]) => ({ feature, score }))
  const parsed = raw.map((item) => {
    const object = asObject(item)
    const name = asString(object.feature) || asString(object.name) || asString(object.reason)
    const numeric = object.shap_value ?? object.shap ?? object.contribution ?? object.score ?? object.value
    return { name, score: typeof numeric === 'number' && Number.isFinite(numeric) ? numeric : null }
  }).filter((item) => item.name && item.score !== null)
  if (!parsed.length) return <EvidenceData value={value} />
  const maximum = Math.max(...parsed.map((item) => Math.abs(item.score ?? 0)), 0.001)
  return <div className="space-y-3">{parsed.map((item, i) => <div key={`${item.name}-${i}`}>
    <div className="mb-1 flex justify-between gap-3 text-sm"><span>{item.name}</span><span className="font-mono">{item.score?.toFixed(3)}</span></div>
    <div className="h-3 overflow-hidden rounded bg-slate-100"><div className={`h-full ${item.score! >= 0 ? 'bg-red-600' : 'bg-blue-600'}`} style={{ width: `${Math.abs(item.score!) / maximum * 100}%` }} /></div>
  </div>)}</div>
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
  const findings: Finding[] = Array.isArray(report.findings) ? report.findings.map((item) => {
    const object = asObject(item)
    return { claim: asString(object.claim), evidence_ids: asStrings(object.evidence_ids) }
  }) : []
  const typologies: Typology[] = Array.isArray(report.typology_matches) ? report.typology_matches.map((item) => {
    const object = asObject(item)
    return { typology: asString(object.typology), explanation: asString(object.explanation), evidence_id: asString(object.evidence_id), chunk_ids: asStrings(object.chunk_ids) }
  }) : []
  const evidenceById = useMemo(() => new Map((query.data?.evidence ?? []).map(item => [item.evidence_id, item])), [query.data?.evidence])
  const active: Evidence | undefined = selected ? evidenceById.get(selected) : undefined
  const citations = (ids: string[]) => ids.map(ref => <button key={ref} type="button" onClick={() => setSelected(ref)} className="rounded border border-blue-200 bg-blue-50 px-2 py-1 font-mono text-xs text-blue-800 hover:bg-blue-100" aria-label={`Inspect evidence ${ref}`}>[{evidenceLabel(ref)}]</button>)

  return <section className="space-y-5">
    <Link to="/queue" className="text-sm text-blue-700 underline">Back to alert queue</Link>
    {!valid && <p role="alert">Invalid case ID.</p>}
    {query.isPending && valid && <div role="status" className="space-y-3">{[1, 2, 3].map(i => <div key={i} className="h-16 animate-pulse rounded bg-slate-200" />)}<span className="sr-only">Loading case</span></div>}
    {query.isError && <div role="alert" className="rounded border border-red-300 bg-red-50 p-4">Could not load case: {query.error.message}<button className="ml-3 underline" onClick={() => void query.refetch()}>Retry</button></div>}
    {query.data && <>
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
      <header className="rounded-xl bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-2xl font-bold">Case #{query.data.case_id}</h1><span className="rounded bg-amber-100 px-3 py-1 text-sm font-semibold">{query.data.status}</span></div>
        <p className="mt-2 text-slate-600">Account {query.data.account_token} Â· Alert #{query.data.alert_id}</p>
        <div className="mt-4 grid gap-3 text-sm md:grid-cols-3"><div><b>Risk score:</b> {(query.data.risk_score * 100).toFixed(1)}%</div><div><b>Model:</b> {query.data.model_version}</div><div><b>Prompt version:</b> {query.data.prompt_version ?? 'Unavailable'}</div><div><b>Risk rating:</b> {asString(report.risk_rating) || 'Unavailable'}</div><div><b>Recommended action:</b> {asString(report.recommended_action) || 'Unavailable'}</div><div><b>Confidence:</b> {typeof report.confidence === 'number' ? `${(report.confidence * 100).toFixed(0)}%` : 'Unavailable'}</div></div>
      </header>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(280px,380px)]">
        <div className="space-y-5">
          <section className="rounded-xl bg-white p-5"><h2 className="mb-3 text-lg font-semibold">Investigation summary</h2><p className="whitespace-pre-wrap">{asString(report.summary) || 'No report summary available.'}</p></section>
          <section className="rounded-xl bg-white p-5"><h2 className="mb-3 text-lg font-semibold">Findings and citations</h2>{findings.length ? <ol className="list-decimal space-y-4 pl-5">{findings.map((finding, i) => <li key={i}><p>{finding.claim}</p><div className="mt-2 flex flex-wrap gap-2">{citations(finding.evidence_ids)}</div></li>)}</ol> : <p>No findings available.</p>}</section>
          <section className="rounded-xl bg-white p-5"><h2 className="mb-3 text-lg font-semibold">Typology matches</h2>{typologies.length ? <div className="space-y-4">{typologies.map((item, i) => <div key={i} className="border-b pb-3"><h3 className="font-semibold">{item.typology}</h3><p className="mt-1 text-sm">{item.explanation}</p><div className="mt-2 flex flex-wrap gap-2">{citations(item.evidence_id ? [item.evidence_id] : [])}{item.chunk_ids.map(chunk => <span key={chunk} className="rounded bg-slate-100 px-2 py-1 font-mono text-xs">Chunk {chunk}</span>)}</div></div>)}</div> : <p>No typology matches recorded.</p>}</section>
          <section className="rounded-xl bg-white p-5"><h2 className="mb-3 text-lg font-semibold">Model reasons / SHAP</h2><p className="mb-3 text-xs text-slate-500">Bars display supplied numeric contributions where available; otherwise the stored reasons are shown as-is.</p><Reasons value={query.data.model_reasons} /></section>
          <section className="rounded-xl bg-white p-5"><h2 className="mb-3 text-lg font-semibold">Open questions</h2><ul className="list-disc space-y-2 pl-5">{asStrings(report.open_questions).map((question, i) => <li key={i}>{question}</li>)}</ul>{!asStrings(report.open_questions).length && <p>No open questions recorded.</p>}</section>
          <section className="rounded-xl border border-amber-200 bg-amber-50 p-5"><h2 className="mb-3 text-lg font-semibold">Evidence and safety warnings</h2><ul className="list-disc space-y-2 pl-5">{query.data.warnings.map((warning, i) => <li key={i}>{warning}</li>)}<li>AI-generated findings are investigative leads, not proof of wrongdoing.</li><li>PII reveal is disabled until separate authorization and audit-write verification is implemented.</li></ul></section>
        </div>
        <aside className="self-start rounded-xl border bg-white p-5 lg:sticky lg:top-4" aria-label="Evidence inspector"><h2 className="mb-3 text-lg font-semibold">Evidence inspector</h2>{!selected ? <><p className="mb-3 text-sm text-slate-500">Select a citation to inspect its source.</p><div className="flex flex-wrap gap-2">{query.data.evidence.filter(isValidEvidence).map(item => <button key={item.evidence_id} onClick={() => setSelected(item.evidence_id)} className="rounded border px-2 py-1 font-mono text-xs">{evidenceLabel(item.evidence_id)}</button>)}</div></> : isValidEvidence(active) ? <div className="space-y-3"><p className="break-all font-mono text-xs">{active.evidence_id}</p><p><b>Source:</b> {active.source}</p><p>{active.summary}</p><EvidenceData value={active.data} /></div> : <div role="alert" className="rounded bg-amber-50 p-3 text-sm">Evidence reference {selected} is not present in the stored case trace.</div>}</aside>
      </div>
    </>}
  </section>
}
