import { test, expect, loginAsMockUser, loginAsAdmin, logoutMockUser } from '../fixtures';
import { apiGet, apiPut } from '../api-helpers';

// Covers ProfileSetupPage (frontend issues #95, #97, #98, #99, #100).
test.describe('ProfileSetupPage', () => {
  test('redirects an unauthenticated user to login (#100)', async ({ page }) => {
    await page.goto('/profile/setup');

    await expect(page).toHaveURL(/\/login$/);
  });

  test('saves the profile and redirects to the dashboard (#95)', async ({ page }) => {
    await loginAsMockUser(page, '/profile/setup');

    await page.getByLabel('Display Name').fill('Loreto Coloma');
    await page.getByLabel('Short Bio').fill('Neighborhood tool sharer.');
    await page.getByRole('button', { name: 'Save Profile' }).click();

    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 5000 });
  });

  test('rejects a blank display name (#97)', async ({ page }) => {
    await loginAsMockUser(page, '/profile/setup');

    const displayNameInput = page.getByLabel('Display Name');
    await displayNameInput.fill('   ');
    await page.getByRole('button', { name: 'Save Profile' }).click();

    await expect(page.locator('.form-error')).toHaveText('Display name is required.');
  });

  test('rejects a display name over the 40-character limit (#98)', async ({ page }) => {
    await loginAsMockUser(page, '/profile/setup');

    await page.getByLabel('Display Name').fill('A'.repeat(41));
    await page.getByRole('button', { name: 'Save Profile' }).click();

    await expect(page.locator('.form-error')).toContainText(
      'must be 40 characters or fewer',
    );
  });

  test.fixme('rejects an unsupported profile photo type (#99)', async ({ page }) => {
    // Real ProfileSetupPage has no profile photo upload field.
    await loginAsMockUser(page, '/profile/setup');

    await page.getByLabel('Profile Photo').setInputFiles({
      name: 'notes.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('not an image'),
    });

    await expect(page.locator('.form-error')).toContainText(
      'must be a JPG, PNG, or WebP image',
    );
  });

  test.fixme('rejects a profile photo larger than 2 MB (#99)', async ({ page }) => {
    // Real ProfileSetupPage has no profile photo upload field.
    await loginAsMockUser(page, '/profile/setup');

    await page.getByLabel('Profile Photo').setInputFiles({
      name: 'huge-photo.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.alloc(2 * 1024 * 1024 + 1),
    });

    await expect(page.locator('.form-error')).toContainText('must be 2 MB or smaller');
  });

  // Regression test for a bug Loreto found in manual testing (issue #271):
  // a brand-new user's setup page can show a PREVIOUS user's bio. Root
  // cause (ProfileSetupPage.tsx): every successful save writes the bio to
  // a single, unscoped localStorage key (`mockUserProfile`), and the page
  // falls back to that cached value whenever the backend's own bio is
  // null -- but unlike the adjacent `profileSetupComplete` flag, that
  // fallback has no `cachedProfile.userId === currentUser.id` ownership
  // check. Logout only clears auth tokens, never this cache, so it
  // survives a full login/logout/login cycle in the same browser.
  test.fail(
    "BUG: a previous user's bio leaks into a different user's setup page (#271)",
    async ({ page }) => {
      const leakedBio = `admin-private-bio-${Date.now()}`;

      // User A (admin) saves a distinctive bio -- this writes it to both
      // the backend and the unscoped localStorage cache.
      await loginAsAdmin(page, '/profile/setup');
      await page.getByLabel('Short Bio').fill(leakedBio);
      await page.getByRole('button', { name: 'Save Profile' }).click();
      await expect(page).toHaveURL(/\/dashboard$/, { timeout: 5000 });

      // Same browser, different user: logout clears tokens only, never
      // the profile cache, then log in as someone else entirely.
      await logoutMockUser(page);
      await loginAsMockUser(page);

      // Force a known-clean starting point regardless of what earlier
      // tests in this suite already saved for this account.
      await apiPut(page, '/api/v1/auth/me', { bio: null });
      const me = await apiGet<{ bio: string | null }>(page, '/api/v1/auth/me');
      expect(me.bio).toBeNull();

      await page.goto('/profile/setup');

      // Should be blank -- User B never set a bio. Currently shows User A's.
      await expect(page.getByLabel('Short Bio')).toHaveValue('');
    },
  );
});
