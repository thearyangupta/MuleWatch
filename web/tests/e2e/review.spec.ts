import { test, expect } from '@playwright/test'

// Browser-flow test with deterministic API fixtures; NOT a live database integration test.
test('login, open case, approve and see status change', async ({ page }) => {
  let approved = false
  await page.route('**/api/auth/token', async route => route.fulfill({ json: { access_token: 'fixture-token', token_type: 'bearer' } }))
  await page.route('**/api/auth/me', async route => route.fulfill({ json: { username: 'fixture', role: 'analyst' } }))
  await page.route('**/api/cases?**', async route => route.fulfill({ json: {
    items: [{ id: 1, alert_id: 7, alert_date: '2026-10-01', account_id: 'synthetic001', risk_score: 0.8, risk: 'HIGH',
      status: approved ? 'CLOSED' : 'AWAITING_REVIEW', summary: null, agent_action: 'CLOSE_NO_ACTION', final_action: null,
      reviewer_id: null, reviewed_at: null, agreement: null, created_at: '2026-10-01T00:00:00Z' }],
    page: 1, page_size: 20, total: 1, total_pages: 1,
  }}))
  await page.route('**/api/cases/1/evidence', async route => route.fulfill({ json: {
    case_id: 1, alert_id: 7, account_token: '****c001', status: approved ? 'CLOSED' : 'AWAITING_REVIEW', risk_score: 0.8,
    model_version: 'fixture', prompt_version: null, report: { recommended_action: 'CLOSE_NO_ACTION', summary: 'Synthetic fixture' },
    evidence: [], model_reasons: [], tool_trace: [], warnings: [],
  }}))
  await page.route('**/api/cases/1/audit', async route => route.fulfill({ json: {
    case_id: 1, alert_id: 7, case_status: approved ? 'CLOSED' : 'AWAITING_REVIEW', chain_valid: true,
    verification_message: 'fixture', event_count: 0, events: [],
  }}))
  await page.route('**/api/cases/1/decision', async route => {
    approved = true
    await route.fulfill({ json: { status: 'CLOSED' } })
  })
  await page.goto('/')
  await page.getByLabel(/username/i).fill('fixture')
  await page.getByLabel(/password/i).fill('fixture-password')
  await page.getByRole('button', { name: /sign in|log in|login/i }).click()
  await expect(page.getByText('Alert Queue')).toBeVisible()
  await page.getByRole('button', { name: 'Open case' }).click()
await expect(page).toHaveURL(/\/cases\/1$/)
  await expect(page.getByText('AWAITING_REVIEW').first()).toBeVisible()
  await page.getByPlaceholder(/explain the decision/i).fill('Evidence reviewed')
  await page.getByRole('button', { name: /submit decision/i }).click()
  await expect(page.getByText('CLOSED').first()).toBeVisible()
})
