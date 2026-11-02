import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DecisionForm } from '../src/components/DecisionForm'
vi.mock('../src/api/client', () => ({ submitCaseDecision: vi.fn().mockResolvedValue(undefined) }))
afterEach(cleanup)
it('requires a comment', async () => {
  const user = userEvent.setup()
  render(<DecisionForm caseId={1} status="AWAITING_REVIEW" recommendedAction="CLOSE_NO_ACTION" onSuccess={() => {}} />)
  const submit = screen.getByRole('button', { name: /submit decision/i })
  expect(submit).toBeDisabled()
  await user.type(screen.getByPlaceholderText(/explain the decision/i), 'Reviewed evidence')
  expect(submit).toBeEnabled()
})
it('requires a different override action', async () => {
  const user = userEvent.setup()
  render(<DecisionForm caseId={1} status="AWAITING_REVIEW" recommendedAction="CLOSE_NO_ACTION" onSuccess={() => {}} />)
  await user.click(screen.getByRole('radio', { name: /override/i }))
  await user.type(screen.getByPlaceholderText(/explain the decision/i), 'Different action warranted')
  expect(screen.getByRole('button', { name: /submit decision/i })).toBeDisabled()
  await user.selectOptions(screen.getByRole('combobox', { name: /final action/i }), 'ENHANCED_MONITORING')
  expect(screen.getByRole('button', { name: /submit decision/i })).toBeEnabled()
})
