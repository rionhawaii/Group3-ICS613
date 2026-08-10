import { test, expect, loginAsMockUser, loginAsMember01 } from '../fixtures';
import { createPickedUpTool, createTestTool, getToolId } from '../api-helpers';

// Covers EditToolPage / US9 + US10 (frontend issues #114, #115, #118, #120,
// #122 and the US10 deactivate/reactivate flows).
//
// Seeded fixture reference (backend/scripts/seed_dev.py):
// - "Cordless Drill" and "Ladder": owned by member01. "Ladder" has an
//   active PICKED_UP reservation (res_c) -- the only seeded tool that's
//   currently out on loan.
// - "Hammer", "Screwdriver", etc.: owned by member02 (the loginAsMockUser
//   account), none of which are PICKED_UP.
//
// Tests that only read state reuse these seeded tools. Tests that save,
// deactivate, or otherwise mutate a listing create their own disposable
// tool via createTestTool() instead, so this file never alters the shared
// seed data other spec files depend on.
test.describe('EditToolPage', () => {
  test('shows a not-found message for an unknown tool id', async ({ page }) => {
    // Must be a well-formed but nonexistent UUID -- a non-UUID string like
    // "does-not-exist" trips FastAPI's path-param validation (422) instead
    // of the service layer's clean 404 "Tool not found".
    await loginAsMockUser(page, '/tools/00000000-0000-0000-0000-000000000000/edit');

    await expect(page.getByRole('heading', { name: 'Tool not found' })).toBeVisible();
  });

  test('shows an owner-only warning for a listing owned by someone else', async ({ page }) => {
    await loginAsMockUser(page); // member02
    const drillId = await getToolId(page, 'Cordless Drill'); // owned by member01

    await page.goto(`/tools/${drillId}/edit`);

    await expect(page.getByRole('heading', { name: 'Access Denied' })).toBeVisible();
    await expect(page.getByText('Only the tool owner can edit this listing.')).toBeVisible();
  });

  test('blocks all edits while the tool is PICKED_UP', async ({ page }) => {
    // A fresh, guaranteed-PICKED_UP tool -- seeded fixtures drift under
    // repeated e2e runs against a shared, non-reset backend (see
    // createPickedUpTool's doc comment).
    await loginAsMember01(page, '/dashboard');
    const { toolId } = await createPickedUpTool(page, `E2E Picked Up ${Date.now()}`);

    await page.goto(`/tools/${toolId}/edit`);

    await expect(
      page.getByRole('heading', { name: 'Editing temporarily unavailable' }),
    ).toBeVisible();
    await expect(page.getByLabel('Tool Name *')).toBeDisabled();
    await expect(page.getByRole('button', { name: 'Save Changes' })).toBeDisabled();
  });

  test('saves an edit successfully for an unblocked listing', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E Edit Target ${Date.now()}`);

    await page.goto(`/tools/${tool.id}/edit`);
    // Wait for the owner's async PICKED_UP-status check to resolve first --
    // otherwise editBlocked is still true from isCheckingLoanStatus and
    // interacting with the (still-disabled) form is a no-op.
    await expect(page.getByLabel('Tool Name *')).toBeEnabled();
    const newDescription = `Updated via e2e ${Date.now()}`;
    await page.getByLabel('Description *').fill(newDescription);
    await page.getByRole('button', { name: 'Save Changes' }).click();

    await expect(page.locator('.form-success')).toHaveText('Tool listing updated successfully.');
    await expect(page.getByLabel('Description *')).toHaveValue(newDescription);
  });

  test('rejects a blank tool name', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E Blank Name ${Date.now()}`);

    await page.goto(`/tools/${tool.id}/edit`);
    await expect(page.getByLabel('Tool Name *')).toBeEnabled();
    await page.getByLabel('Tool Name *').fill('');
    await page.getByRole('button', { name: 'Save Changes' }).click();

    await expect(page.locator('.form-error')).toHaveText('Tool name is required.');
  });

  // BUG found while rewriting this suite against the real API: unlike
  // ToolService.create_tool (which rejects a duplicate name with 409 "You
  // already have an active listing with this name"), update_tool
  // (backend/src/app/services/tool.py:387-429) has no equivalent
  // uniqueness check at all -- renaming a listing to match another of the
  // same owner's listings silently succeeds. Both tools here are disposable
  // e2e fixtures, so letting the rename actually go through is harmless.
  test.fail(
    "BUG: renaming a listing to a name already used by another of your own listings isn't rejected (#120)",
    async ({ page }) => {
      await loginAsMockUser(page, '/dashboard');
      const suffix = Date.now();
      const existing = await createTestTool(page, `E2E Existing Name ${suffix}`);
      const target = await createTestTool(page, `E2E Rename Target ${suffix}`);

      await page.goto(`/tools/${target.id}/edit`);
      await expect(page.getByLabel('Tool Name *')).toBeEnabled();
      await page.getByLabel('Tool Name *').fill(existing.name);
      await page.getByRole('button', { name: 'Save Changes' }).click();

      await expect(page.locator('.form-error')).toContainText('already have');
    },
  );

  test('cannot remove the last remaining photo', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E One Photo ${Date.now()}`);

    await page.goto(`/tools/${tool.id}/edit`);
    await expect(page.getByLabel('Tool Name *')).toBeEnabled();

    await expect(page.getByRole('button', { name: 'Remove' })).toBeDisabled();
    await expect(page.getByText('At least one photo must remain.')).toBeVisible();
  });

  test('rejects an unsupported photo file type when adding a photo', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E Bad Photo Type ${Date.now()}`);

    await page.goto(`/tools/${tool.id}/edit`);
    // Wait for the owner's async PICKED_UP-status check to resolve --
    // otherwise editBlocked is still true from isCheckingLoanStatus and
    // this trips the loan-status guard instead of the photo validation.
    await expect(page.getByLabel('Add Photos')).toBeEnabled();
    await page.getByLabel('Add Photos').setInputFiles({
      name: 'notes.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('not an image'),
    });

    await expect(page.locator('.form-error')).toContainText(
      'is not a supported image. Photos must be JPG, PNG, or WebP.',
    );
  });

  test('deactivates a listing with a reason', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E Deactivate Me ${Date.now()}`);

    await page.goto(`/tools/${tool.id}/edit`);
    await expect(page.getByLabel('Tool Name *')).toBeEnabled();
    await page.getByLabel('Reason *').fill('Testing deactivation via e2e.');
    await page.getByRole('button', { name: 'Deactivate Listing' }).click();

    await expect(page.locator('.form-success')).toHaveText('Tool deactivated successfully.');
    await expect(page.locator('p').filter({ hasText: 'Status:' })).toContainText('Deactivated');
  });

  test('requires a reason before deactivating', async ({ page }) => {
    await loginAsMockUser(page, '/dashboard');
    const tool = await createTestTool(page, `E2E No Reason ${Date.now()}`);

    await page.goto(`/tools/${tool.id}/edit`);
    await expect(page.getByLabel('Tool Name *')).toBeEnabled();
    await page.getByRole('button', { name: 'Deactivate Listing' }).click();

    await expect(page.locator('.form-error')).toHaveText('A deactivation reason is required.');
  });

  // Real EditToolPage has no delete-listing control at all -- only
  // Deactivate/Reactivate. DELETE /api/v1/tools/{id} exists on the backend
  // (ToolService.delete_tool) and is covered by the acceptance suite, but
  // nothing in the frontend calls it from this or any other page.
  test.fixme('owner can delete the listing after typing DELETE', async () => {
    // Not implemented: no delete UI exists on EditToolPage.
  });
});
