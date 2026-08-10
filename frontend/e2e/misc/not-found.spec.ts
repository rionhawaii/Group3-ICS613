import { test, expect, loginAsMockUser } from '../fixtures';

test.describe('NotFoundPage', () => {
  test('shows a 404 page for an unknown route and links back to the dashboard', async ({
    page,
  }) => {
    // Log in first: /dashboard is behind RequireAuth, so an anonymous user
    // clicking "Back to Dashboard" is redirected to /login and the final URL
    // assertion races the redirect.
    await loginAsMockUser(page, '/dashboard');
    await page.goto('/this-route-does-not-exist');

    await expect(page.getByRole('heading', { name: 'Page Not Found' })).toBeVisible();

    await page.getByRole('link', { name: 'Back to Dashboard' }).click();

    await expect(page).toHaveURL(/\/dashboard$/);
  });
});
