import { test, expect, loginAsAdmin, loginAsMockUser } from '../fixtures';
import {
  apiGet,
  apiPost,
  createPickedUpTool,
  createTestTool,
  type PaginatedResult,
} from '../api-helpers';

// Covers AdminListingsPage / US11 (admin deactivate/reactivate controls).
//
// The real page has no PICKED_UP-blocked summary count or audit-log card
// (those were mock-only UI) -- just Total/Active/Deactivated. Deactivation
// still fails server-side for a PICKED_UP tool (ToolService.deactivate_tool),
// surfaced through the same actionMessage paragraph as a success message.
interface ToolSummary {
  id: string;
  name: string;
  is_active: boolean;
}

// AdminListingsPage has no request-sequencing guard on fetchTools -- its
// own unfiltered mount-time fetch can resolve *after* a filter applied
// moments later and silently overwrite the filtered result with it. Wait
// for that initial fetch to settle before touching any filter or action.
async function waitForInitialLoad(page: import('@playwright/test').Page) {
  await expect(page.getByText('Loading listings...')).toHaveCount(0);
}

test.describe('AdminListingsPage', () => {
  test('shows summary counts matching the first page of the real API response', async ({
    page,
  }) => {
    await loginAsAdmin(page);
    // AdminListingsPage computes Active/Deactivated from just the current
    // page of results (DEFAULT_PAGE_SIZE = 20), not a true global count --
    // replicate that exactly rather than asserting against every listing.
    const firstPage = await apiGet<PaginatedResult<ToolSummary>>(
      page,
      '/api/v1/tools/admin/all?page=1&page_size=20',
    );
    const activeCount = firstPage.items.filter((t) => t.is_active).length;
    const deactivatedCount = firstPage.items.filter((t) => !t.is_active).length;

    await page.goto('/admin/listings');

    const summaryCards = page.locator('.admin-listing-summary-grid .summary-card');
    await expect(summaryCards.nth(0)).toContainText(String(firstPage.total));
    await expect(summaryCards.nth(1)).toContainText(String(activeCount));
    await expect(summaryCards.nth(2)).toContainText(String(deactivatedCount));
  });

  // The backend rejects deactivating any tool with an active PICKED_UP
  // reservation, admin included. Uses a freshly-created, guaranteed
  // PICKED_UP fixture rather than the seeded "Ladder" -- that seed row
  // drifts under repeated e2e runs against a shared, non-reset backend
  // (other tests return it, re-deactivate it, etc.), so it isn't a
  // reliable precondition.
  test('a listing with a PICKED_UP reservation cannot be deactivated', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const name = `E2E Picked Up Admin ${Date.now()}`;
    await createPickedUpTool(page, name);

    await loginAsAdmin(page, '/admin/listings');
    await waitForInitialLoad(page);
    await page.getByLabel('Search Listings').fill(name);

    const card = page.locator('.admin-listing-card', { hasText: name });
    await card.getByLabel('Reason *').fill('Attempting to deactivate a loaned tool.');
    await card.getByRole('button', { name: 'Deactivate' }).click();

    await expect(page.locator('.success-message')).toContainText(
      'Cannot deactivate a tool that is currently borrowed (PICKED_UP)',
    );
  });

  test('the Deactivate button stays disabled until a reason is entered', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E Admin List ${Date.now()}`);

    await loginAsAdmin(page, '/admin/listings');
    await waitForInitialLoad(page);
    await page.getByLabel('Search Listings').fill(tool.name);
    const card = page.locator('.admin-listing-card', { hasText: tool.name });

    await expect(card.getByRole('button', { name: 'Deactivate' })).toBeDisabled();
    await card.getByLabel('Reason *').fill('Now it has a reason.');
    await expect(card.getByRole('button', { name: 'Deactivate' })).toBeEnabled();
  });

  test('deactivates a listing with a reason', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E Deactivate ${Date.now()}`);

    await loginAsAdmin(page, '/admin/listings');
    await waitForInitialLoad(page);
    await page.getByLabel('Search Listings').fill(tool.name);
    const card = page.locator('.admin-listing-card', { hasText: tool.name });
    await card.getByLabel('Reason *').fill('Reported as unsafe by a member.');
    await card.getByRole('button', { name: 'Deactivate' }).click();

    await expect(page.locator('.success-message')).toContainText(`${tool.name} deactivated.`);
    await expect(card.locator('.admin-listing-status')).toHaveText('deactivated');
  });

  test('reactivates an already-deactivated listing', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E Reactivate ${Date.now()}`);

    // Deactivate it first via the same admin flow being tested elsewhere,
    // so this test is self-contained regardless of run order.
    await loginAsAdmin(page, '/admin/listings');
    await waitForInitialLoad(page);
    await page.getByLabel('Search Listings').fill(tool.name);
    let card = page.locator('.admin-listing-card', { hasText: tool.name });
    await card.getByLabel('Reason *').fill('Setup for reactivate test.');
    await card.getByRole('button', { name: 'Deactivate' }).click();
    await expect(card.locator('.admin-listing-status')).toHaveText('deactivated');

    card = page.locator('.admin-listing-card', { hasText: tool.name });
    await card.getByRole('button', { name: 'Reactivate' }).click();

    await expect(page.locator('.success-message')).toContainText(`${tool.name} reactivated.`);
    await expect(card.locator('.admin-listing-status')).toHaveText('active');
  });

  test('filters listings by search text', async ({ page }) => {
    await loginAsAdmin(page, '/admin/listings');
    await waitForInitialLoad(page);

    await page.getByLabel('Search Listings').fill('Pliers');

    await expect(page.locator('.admin-listing-card')).toHaveCount(1);
    await expect(page.locator('.admin-listing-card')).toContainText('Pliers');
  });

  test('filters listings by status', async ({ page }) => {
    // No seeded tool starts deactivated, and this must hold regardless of
    // what other tests have or haven't run yet -- guarantee at least one
    // deactivated listing exists rather than relying on run order. Other
    // tests in this file deactivate/reactivate their own disposable tools
    // concurrently, so the *global* inactive count is inherently racy
    // under parallel workers -- combine the status filter with a search
    // for this test's own unique tool name instead of asserting over
    // whatever else happens to be inactive at that instant.
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E Status Filter ${Date.now()}`);
    await apiPost(page, `/api/v1/tools/${tool.id}/deactivate`, {
      reason: 'Setup for status-filter test.',
    });

    await loginAsAdmin(page, '/admin/listings');
    await waitForInitialLoad(page);
    const cards = page.locator('.admin-listing-card');

    // Apply only one filter (status) rather than chaining it after search
    // -- two filter changes in quick succession would just reintroduce
    // the same stale-response race waitForInitialLoad exists to avoid.
    await page.getByLabel('Status Filter').selectOption('inactive');

    const ownCard = cards.filter({ hasText: tool.name });
    await expect(ownCard).toBeVisible();
    await expect(ownCard.locator('.admin-listing-status')).toHaveText('deactivated');
  });
});
