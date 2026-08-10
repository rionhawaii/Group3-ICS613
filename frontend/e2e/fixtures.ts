import type { Page } from '@playwright/test';

export { test, expect } from '@playwright/test';

/**
 * Login helper for tests that need an authenticated session.
 *
 * Since the app now talks to a real backend API (not a mock/localStorage-only
 * SPA), this helper calls POST /login to get a real access token and stores
 * it in localStorage the same way the real LoginPage does, so all subsequent
 * API calls are properly authenticated.
 *
 * The seeded test account is used:
 *   email: member02@example.com
 *   password: devpass123
 *
 * After login, navigates to `path` so tests land on the correct page.
 */
export async function loginAsMockUser(page: Page, path = '/dashboard') {
  await page.goto('/login');
  await page.getByLabel('Email').fill('member02@example.com');
  await page.getByLabel('Password').fill('devpass123');
  await page.getByRole('button', { name: 'Login' }).click();
  // Wait for login to complete and redirect
  await page.waitForURL(/\/dashboard$/);
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'));
  if (!token) {
    throw new Error('Login did not produce an access_token in localStorage');
  }
  // Navigate to the requested page (skip if already on /dashboard).
  if (path !== '/dashboard') {
    await page.goto(path);
  }
}

/**
 * Login as the seeded "Demo Owner" account (member01@example.com).
 *
 * Distinct from loginAsMockUser (member02@example.com) -- some scenarios
 * need to be logged in as the specific owner of a particular seeded tool
 * (see scripts/seed_dev.py: even-indexed tools, e.g. "Cordless Drill" and
 * "Ladder", are owned by member01; odd-indexed ones by member02).
 */
export async function loginAsMember01(page: Page, path = '/dashboard') {
  await page.goto('/login');
  await page.getByLabel('Email').fill('member01@example.com');
  await page.getByLabel('Password').fill('devpass123');
  await page.getByRole('button', { name: 'Login' }).click();
  await page.waitForURL(/\/dashboard$/);
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'));
  if (!token) {
    throw new Error('Login did not produce an access_token in localStorage');
  }
  if (path !== '/dashboard') {
    await page.goto(path);
  }
}

/**
 * Login as the seeded admin user for tests that need admin privileges.
 *
 * Uses:
 *   email: admin@example.com
 *   password: devpass123
 */
export async function loginAsAdmin(page: Page, path = '/dashboard') {
  await page.goto('/login');
  await page.getByLabel('Email').fill('admin@example.com');
  await page.getByLabel('Password').fill('devpass123');
  await page.getByRole('button', { name: 'Login' }).click();
  await page.waitForURL(/\/dashboard$/);
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'));
  if (!token) {
    throw new Error('Login did not produce an access_token in localStorage');
  }
  if (path !== '/dashboard') {
    await page.goto(path);
  }
}

export async function logoutMockUser(page: Page) {
  await page.goto('/login');
  await page.evaluate(() => {
    window.localStorage.removeItem('access_token');
    window.localStorage.removeItem('refresh_token');
  });
}
