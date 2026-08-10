import { test, expect, loginAsMockUser } from '../fixtures';
import { FAKE_PNG } from '../api-helpers';

// Covers CreateToolPage / US8 (frontend issues #114, #115, #117, #118, #120).
// The form uses noValidate, so all JS validation branches are reachable
// through a normal submit click.
test.describe('CreateToolPage', () => {
  async function fillRequiredFields(page: import('@playwright/test').Page, name: string) {
    await page.getByLabel('Tool Name *').fill(name);
    await page.getByLabel('Category *').selectOption('POWER_TOOLS');
    await page.getByLabel('Condition *').selectOption('GOOD');
    await page.getByLabel('Description *').fill('A tool used for the E2E demo.');
  }

  test('rejects submission with all required fields missing (#114)', async ({ page }) => {
    await loginAsMockUser(page, '/tools/new');

    await page.getByRole('button', { name: 'Create Tool Listing' }).click();

    await expect(page.locator('.form-error')).toHaveText('Tool name is required.');
  });

  test('rejects a listing with zero photos (#117)', async ({ page }) => {
    await loginAsMockUser(page, '/tools/new');

    await fillRequiredFields(page, `E2E No Photo ${Date.now()}`);
    await page.getByRole('button', { name: 'Create Tool Listing' }).click();

    await expect(page.locator('.form-error')).toHaveText('At least one photo is required.');
  });

  // member02 (the loginAsMockUser account) already owns a seeded "Hammer"
  // listing (scripts/seed_dev.py) -- uniqueness is scoped per-owner, so
  // submitting another "Hammer" while logged in as member02 collides.
  test('rejects a duplicate listing name (#120)', async ({ page }) => {
    await loginAsMockUser(page, '/tools/new');

    await fillRequiredFields(page, 'Hammer');
    await page.getByLabel('Tool Photos').setInputFiles(FAKE_PNG);
    await page.getByRole('button', { name: 'Create Tool Listing' }).click();

    await expect(page.locator('.form-error')).toHaveText(
      'You already have a listing with that name.',
    );
  });

  test('rejects an unsupported photo file type (#115)', async ({ page }) => {
    await loginAsMockUser(page, '/tools/new');

    await page.getByLabel('Tool Photos').setInputFiles({
      name: 'notes.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('not an image'),
    });

    await expect(page.locator('.form-error')).toContainText(
      'Photos must be JPG, PNG, or WebP.',
    );
  });

  test('creates a listing successfully with a valid photo', async ({ page }) => {
    await loginAsMockUser(page, '/tools/new');
    const name = `E2E Brand New Tool ${Date.now()}`;

    await fillRequiredFields(page, name);
    await page.getByLabel('Tool Photos').setInputFiles(FAKE_PNG);
    await page.getByRole('button', { name: 'Create Tool Listing' }).click();

    await expect(page.locator('.success-message')).toContainText(`Tool listing created: ${name}`);
    await expect(page).toHaveURL(/\/tools\/[0-9a-f-]{36}$/, { timeout: 3000 });
  });
});
