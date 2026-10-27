import { Link, useParams } from 'react-router'
export function CasePage() {
  const { caseId } = useParams()
  return <section className="space-y-4"><Link className="text-blue-700 underline" to="/queue">Back to alert queue</Link><h2 className="text-2xl font-bold">Case {caseId}</h2><p>Case evidence and review will be implemented on Day 3.</p></section>
}
