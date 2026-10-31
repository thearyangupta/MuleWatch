import { useState, type FormEvent } from 'react'
import {
  submitCaseDecision,
  type FinalAction,
  type ReviewDecision,
} from '../api/client'

type Props = {
  caseId: number
  status: string
  recommendedAction: string
  onSuccess: () => Promise<unknown> | void
}

const actions: FinalAction[] = [
  'CLOSE_NO_ACTION',
  'ENHANCED_MONITORING',
  'ESCALATE_TO_INVESTIGATOR',
]

export function DecisionForm({
  caseId,
  status,
  recommendedAction,
  onSuccess,
}: Props) {
  const [decision, setDecision] = useState<ReviewDecision>('approve')
  const [comment, setComment] = useState('')
  const [finalAction, setFinalAction] = useState<FinalAction | ''>('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

  const canReview = status === 'AWAITING_REVIEW'
  const validOverride =
    decision !== 'override' ||
    (finalAction !== '' && finalAction !== recommendedAction)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')

    if (!canReview || !comment.trim() || !validOverride) return

    setSubmitting(true)

    try {
      await submitCaseDecision(caseId, {
        decision,
        comment: comment.trim(),
        ...(decision === 'override' && finalAction
          ? { final_action: finalAction }
          : {}),
      })

      setSuccess(true)
      await onSuccess()
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Decision failed',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="rounded-xl bg-white p-5">
      <h2 className="mb-3 text-lg font-semibold">Human review decision</h2>

      {!canReview ? (
        <p className="text-sm text-slate-600">
          This case is not awaiting review.
        </p>
      ) : success ? (
        <p role="status" className="text-green-700">
          Decision submitted successfully.
        </p>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <fieldset>
            <legend className="mb-2 font-medium">Decision</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {(['approve', 'override', 'escalate'] as const).map(value => (
                <label
                  key={value}
                  className="flex cursor-pointer items-center gap-2 rounded border p-3"
                >
                  <input
                    type="radio"
                    name="decision"
                    checked={decision === value}
                    onChange={() => setDecision(value)}
                  />
                  <span className="capitalize">{value}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {decision === 'override' && (
            <label className="block space-y-2">
              <span className="font-medium">Final action</span>
              <select
                required
                value={finalAction}
                onChange={event =>
                  setFinalAction(event.target.value as FinalAction | '')
                }
                className="w-full rounded border p-3"
              >
                <option value="">Select a different final action</option>
                {actions
                  .filter(action => action !== recommendedAction)
                  .map(action => (
                    <option key={action} value={action}>
                      {action.replaceAll('_', ' ')}
                    </option>
                  ))}
              </select>
            </label>
          )}

          <label className="block space-y-2">
            <span className="font-medium">Required comment</span>
            <textarea
              required
              maxLength={2000}
              value={comment}
              onChange={event => setComment(event.target.value)}
              className="min-h-28 w-full rounded border p-3"
              placeholder="Explain the decision and supporting evidence"
            />
          </label>

          {error && (
            <p role="alert" className="rounded bg-red-50 p-3 text-red-700">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting || !comment.trim() || !validOverride}
            className="rounded bg-blue-700 px-5 py-3 font-semibold text-white disabled:opacity-50"
          >
            {submitting ? 'Submitting...' : 'Submit decision'}
          </button>
        </form>
      )}
    </section>
  )
}
