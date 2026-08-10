import { test, expect, loginAsAdmin, loginAsMockUser } from '../fixtures';

// Covers AdminModerationReportsPage (User Story 33 / GitHub issue #60),
// wired to the real backend (GET /admin/reports/moderation and
// /admin/reports/moderation/export -- see
// backend/src/app/tests/acceptance/test_us33_moderation_reports.py for the
// API-level contract these UI tests build on).
//
// Replaces the retired admin-moderation-analytics.spec.ts, which covered a
// frontend-only, mock-data duplicate of this page (AdminReport.tsx, later
// renamed AdminModerationAnalyticsPage.tsx) that was removed as redundant
// once this already-wired implementation was found still on main. That page
// also had no admin-nav link at all -- added here alongside this spec.
//
// Tests run against a live, shared backend with no per-test database reset
// (see e2e/api-helpers.ts), so exact summary totals aren't asserted -- only
// that the expected fields render and update.
test.describe('AdminModerationReportsPage', () => {
  test('is reachable from the admin nav', async ({ page }) => {
    await loginAsAdmin(page);

    await page.getByRole('link', { name: 'Moderation Reports' }).click();

    await expect(page).toHaveURL(/\/admin\/moderation\/reports$/);
    await expect(page.getByRole('heading', { name: 'Community Moderation Report' })).toBeVisible();
  });

  test('generates a report and shows summary cards', async ({ page }) => {
    await loginAsAdmin(page, '/admin/moderation/reports');

    await page.getByRole('button', { name: 'Generate Report' }).click();

    await expect(page.getByText('Total Reports')).toBeVisible();
    await expect(page.getByText('Suspensions')).toBeVisible();
    await expect(page.getByText('Tool Deactivations')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Export CSV' })).toBeVisible();
  });

  test('shows an empty state for a date range with no activity', async ({ page }) => {
    await loginAsAdmin(page, '/admin/moderation/reports');

    await page.getByLabel('Date from').fill('2099-01-01');
    await page.getByLabel('Date to').fill('2099-12-31');
    await page.getByRole('button', { name: 'Generate Report' }).click();

    await expect(page.getByText('No records found for the selected date range.')).toBeVisible();
    // Summary cards still render (with zero totals) even when empty.
    await expect(page.getByText('Total Reports')).toBeVisible();
  });

  test('exports the report as a downloadable CSV', async ({ page }) => {
    await loginAsAdmin(page, '/admin/moderation/reports');

    await page.getByRole('button', { name: 'Generate Report' }).click();
    await expect(page.getByRole('button', { name: 'Export CSV' })).toBeVisible();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export CSV' }).click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe('moderation_report.csv');
  });

  test('blocks a non-admin from viewing moderation reports', async ({ page }) => {
    await loginAsMockUser(page, '/admin/moderation/reports');

    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(page.getByRole('link', { name: 'Moderation Reports' })).toHaveCount(0);
  });
});
