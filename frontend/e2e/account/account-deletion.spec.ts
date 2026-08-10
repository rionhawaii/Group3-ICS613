import { test, expect, loginAsMockUser, loginAsAdmin } from '../fixtures';

// Covers AccountDeletionPage (frontend issues #105, #107).
//
// The real page checks active reservations via 6 parallel API calls
// (borrower/owner x REQUESTED/APPROVED/PICKED_UP) rather than a mock
// toggle. member02 (seed_dev.py) already has an active REQUESTED
// reservation as borrower ("Cordless Drill"), so it's used as-is for the
// blocked-by-default case. The validation-only tests use admin instead,
// which owns no tools/reservations in seed data -- its form is fully
// enabled, but neither test supplies BOTH a correct "DELETE" confirmation
// and a checked understanding box, so the real deletion call is never
// reached and the admin account is never actually deleted.
test.describe('AccountDeletionPage', () => {
  test('redirects an unauthenticated user to login', async ({ page }) => {
    await page.goto('/account/delete');

    await expect(page).toHaveURL(/\/login$/);
  });

  test('blocks deletion while active reservations exist by default (#107)', async ({ page }) => {
    await loginAsMockUser(page, '/account/delete');

    await expect(page.getByText('Account deletion is currently blocked')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Delete Account' })).toBeDisabled();
  });

  test('requires typing DELETE before the account can be removed', async ({ page }) => {
    await loginAsAdmin(page, '/account/delete');

    await page.getByLabel('I understand this action cannot be undone.').check();
    await page.getByRole('button', { name: 'Delete Account' }).click();

    await expect(page.locator('.form-error')).toHaveText(
      'Please type DELETE to confirm account deletion.',
    );
  });

  test('requires the final understanding checkbox', async ({ page }) => {
    await loginAsAdmin(page, '/account/delete');

    await page.getByLabel('Type DELETE to Confirm').fill('DELETE');
    await page.getByRole('button', { name: 'Delete Account' }).click();

    await expect(page.locator('.form-error')).toHaveText(
      'Please confirm that you understand this action cannot be undone.',
    );
  });

  // Not implemented (test-infra limitation, not a product gap): completing
  // this scenario needs a disposable account with zero active reservations
  // -- but a genuinely fresh, loginable account needs both a real invite
  // token AND a real email-verification token, and the latter is only ever
  // emailed (AuthService.register, backend/src/app/services/auth.py:166),
  // never returned by any API response. The only loginable accounts this
  // suite has (member01, member02, admin) are shared across every other
  // spec file and can't be sacrificed to test real deletion.
  test.fixme('deletes the account and redirects to login once confirmed', async () => {});
});
