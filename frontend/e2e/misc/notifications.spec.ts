import { test, expect, loginAsMockUser } from '../fixtures';
import { apiGet } from '../api-helpers';

// Covers NotificationsPage (Task 4 notification center) and its sync with
// AppLayout's nav badge / DashboardPage's unread summary card.
//
// Fixture (scripts/seed_dev.py): member02 has 3 notifications, 2 unread and
// 1 read. Tests in this file run in order and share that seeded state
// (there's no per-test database reset in e2e), so later tests build on the
// mutations of earlier ones rather than re-asserting the original counts.
test.describe.serial('NotificationsPage', () => {
  test('shows initial total/unread/read summary counts', async ({ page }) => {
    await loginAsMockUser(page, '/notifications');

    // The suite runs against a live, shared backend with no per-test reset,
    // so other spec files may have added to (or mutated) member02's
    // notifications before this file runs. Fetch the real current counts and
    // assert the summary cards match them, instead of hardcoding the seed
    // fixture values (3 total / 2 unread / 1 read).
    const data = await apiGet<{ total: number; unread_count: number }>(
      page,
      '/api/v1/notifications?page_size=20',
    );

    const summaryCards = page.locator('.notification-summary-grid .summary-card');
    await expect(summaryCards.nth(0).locator('.summary-number')).toHaveText(String(data.total));
    await expect(summaryCards.nth(1).locator('.summary-number')).toHaveText(
      String(data.unread_count),
    );
    await expect(summaryCards.nth(2).locator('.summary-number')).toHaveText(
      String(data.total - data.unread_count),
    );
  });

  test('filters to unread and read notifications', async ({ page }) => {
    await loginAsMockUser(page, '/notifications');

    // Counts are relative to whatever admin/misc specs ran before this file
    // (e.g. admin-listings deactivation/reactivation now notifies the owner),
    // so read the live counts instead of hardcoding the seed fixture values.
    const data = await apiGet<{ total: number; unread_count: number }>(
      page,
      '/api/v1/notifications?page_size=20',
    );
    const unread = data.unread_count;
    const read = data.total - data.unread_count;

    await page.getByRole('button', { name: `Unread (${unread})` }).click();
    await expect(page.locator('.notification-card')).toHaveCount(unread);

    await page.getByRole('button', { name: `Read (${read})` }).click();
    await expect(page.locator('.notification-card')).toHaveCount(read);
  });

  test('marks a single notification as read and updates counts', async ({ page }) => {
    await loginAsMockUser(page, '/notifications');

    const before = await apiGet<{ unread_count: number }>(
      page,
      '/api/v1/notifications?page_size=20',
    );

    await page
      .locator('.notification-card-unread')
      .first()
      .getByRole('button', { name: 'Mark as Read' })
      .click();

    await expect(page.getByText('Notification marked as read.')).toBeVisible();
    await expect(
      page.locator('.notification-summary-grid .summary-card').nth(1).locator('.summary-number'),
    ).toHaveText(String(before.unread_count - 1));
  });

  test('marks all remaining notifications as read and syncs the nav badge and dashboard', async ({
    page,
  }) => {
    // One fewer unread notification remains after the previous test marked
    // a single notification as read.
    await loginAsMockUser(page, '/notifications');

    const remaining = await apiGet<{ unread_count: number }>(
      page,
      '/api/v1/notifications?page_size=20',
    );
    await expect(page.locator('.nav-notification-badge')).toHaveText(
      String(remaining.unread_count),
    );

    await page.getByRole('button', { name: 'Mark All as Read' }).click();

    await expect(page.getByText('All notifications marked as read.')).toBeVisible();
    await expect(page.locator('.notification-card-unread')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Mark All as Read' })).toBeDisabled();
    await expect(page.locator('.nav-notification-badge')).toHaveCount(0);

    await page.goto('/dashboard');
    await expect(page.locator('.notification-unread-summary .summary-number')).toHaveText('0');
  });

  test.fixme(
    'resetting the demo restores the original unread state',
    async () => {
      // Not implemented: NotificationsPage has no "Reset Demo" concept in the
      // real app -- that was an R1 mock-only affordance for replaying the
      // demo. Notifications are now real backend rows with no reset action.
    },
  );
});
