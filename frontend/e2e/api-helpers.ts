import type { Page } from '@playwright/test';

/**
 * Test-only helpers for talking to the real backend API directly from a
 * Playwright test, kept separate from fixtures.ts (login helpers) so this
 * file's only dependency is @playwright/test -- nothing here touches
 * frontend/src.
 *
 * Tests run against a live, shared backend with no per-test database reset,
 * so other spec files can add to (or mutate) the same seeded rows a given
 * test cares about. Rather than hardcoding an expected count that could
 * drift depending on run order, these helpers fetch the real current value
 * so a test can assert the UI matches it.
 */

/** Shape shared by every list endpoint (PaginatedResponse on the backend). */
export interface PaginatedResult<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ToolSummary {
  id: string;
  name: string;
}

export interface ReservationSummary {
  id: string;
  tool_id: string;
  state: string;
}

/** Authenticated GET against the real backend, using the current page's logged-in access token. */
export async function apiGet<T = unknown>(page: Page, path: string): Promise<T> {
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'));
  const response = await page.request.get(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok()) {
    throw new Error(`GET ${path} failed: ${response.status()} ${await response.text()}`);
  }
  return response.json();
}

/** Authenticated DELETE against the real backend, using the current page's logged-in access token. */
export async function apiDelete(page: Page, path: string): Promise<void> {
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'));
  const response = await page.request.delete(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!response.ok() && response.status() !== 404) {
    throw new Error(`DELETE ${path} failed: ${response.status()} ${await response.text()}`);
  }
}

/** Authenticated PUT against the real backend, using the current page's logged-in access token. */
export async function apiPut<T = unknown>(page: Page, path: string, data: unknown): Promise<T> {
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'));
  const response = await page.request.put(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    data,
  });
  if (!response.ok()) {
    throw new Error(`PUT ${path} failed: ${response.status()} ${await response.text()}`);
  }
  return response.json();
}

/** Authenticated POST (JSON body) against the real backend, using the current page's logged-in access token. */
export async function apiPost<T = unknown>(page: Page, path: string, data?: unknown): Promise<T> {
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'));
  const response = await page.request.post(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    data,
  });
  if (!response.ok()) {
    throw new Error(`POST ${path} failed: ${response.status()} ${await response.text()}`);
  }
  return response.json();
}

interface CreatedTool {
  id: string;
  name: string;
  is_active: boolean;
}

/**
 * A real, minimal 1x1 transparent PNG (not just a file with an image/*
 * MIME type) -- the backend sniffs actual file content, not just the
 * client-declared Content-Type, so an arbitrary byte string is rejected
 * with 422 "File contents do not match any supported image format."
 */
export const FAKE_PNG = {
  name: 'e2e-fixture.png',
  mimeType: 'image/png',
  buffer: Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  ),
};

/**
 * Create a disposable tool listing owned by the currently logged-in user,
 * via a real multipart POST /tools (one fake JPEG photo, satisfying the
 * "at least 1 photo" requirement). Used by tests that need to mutate a
 * listing (edit, deactivate, add/remove photos) without touching the
 * shared seed_dev.py fixtures that other spec files depend on.
 */
export async function createTestTool(
  page: Page,
  name: string,
  overrides?: { category?: string; condition?: string; description?: string },
): Promise<CreatedTool> {
  const token = await page.evaluate(() => window.localStorage.getItem('access_token'));
  const response = await page.request.post('/api/v1/tools', {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    multipart: {
      name,
      category: overrides?.category ?? 'POWER_TOOLS',
      condition: overrides?.condition ?? 'GOOD',
      description: overrides?.description ?? 'Created by an e2e test.',
      photos: FAKE_PNG,
    },
  });
  if (!response.ok()) {
    throw new Error(`POST /api/v1/tools failed: ${response.status()} ${await response.text()}`);
  }
  return response.json();
}

async function loginForToken(page: Page, email: string, password = 'devpass123'): Promise<string> { // pragma: allowlist secret -- dev-only seed password, not a real credential
  const response = await page.request.post('/api/v1/auth/login', { data: { email, password } });
  if (!response.ok()) {
    throw new Error(`login failed for ${email}: ${response.status()} ${await response.text()}`);
  }
  const body = (await response.json()) as { access_token: string };
  return body.access_token;
}

/**
 * Create a fresh, disposable tool with a genuinely PICKED_UP reservation on
 * it, via direct API calls with two independent bearer tokens (owner +
 * borrower) -- not tied to whichever account happens to be logged into
 * `page` right now. Needed because the seeded PICKED_UP fixture
 * (scripts/seed_dev.py's "Ladder") drifts under repeated e2e runs against a
 * shared, non-reset backend: other tests return it, re-deactivate it, etc.,
 * so relying on it as a fixed precondition is not reliable.
 */
export async function createPickedUpTool(
  page: Page,
  name: string,
  ownerEmail = 'member01@example.com',
  borrowerEmail = 'member02@example.com',
): Promise<{ toolId: string; reservationId: string }> {
  const ownerToken = await loginForToken(page, ownerEmail);
  const borrowerToken = await loginForToken(page, borrowerEmail);

  const toolResponse = await page.request.post('/api/v1/tools', {
    headers: { Authorization: `Bearer ${ownerToken}` },
    multipart: {
      name,
      category: 'POWER_TOOLS',
      condition: 'GOOD',
      description: 'Created by an e2e test (picked-up fixture).',
      photos: FAKE_PNG,
    },
  });
  if (!toolResponse.ok()) {
    throw new Error(`create tool failed: ${toolResponse.status()} ${await toolResponse.text()}`);
  }
  const tool = (await toolResponse.json()) as CreatedTool;

  // The backend compares reservation dates against "today" in HST
  // (UTC-10), but `Date.toISOString()` is UTC -- for roughly 10 hours a day
  // (evening HST, already tomorrow in UTC) that mismatch sends a start_date
  // one day ahead of the backend's HST "today", and mark-picked-up then
  // rejects it as being before the start date. Shift by the HST offset
  // before slicing so the calendar date always matches the backend's.
  const HST_OFFSET_MS = 10 * 60 * 60 * 1000;
  const fmt = (d: Date) => new Date(d.getTime() - HST_OFFSET_MS).toISOString().slice(0, 10);
  const start = new Date();
  const end = new Date();
  end.setDate(end.getDate() + 5);

  const resResponse = await page.request.post('/api/v1/reservations', {
    headers: { Authorization: `Bearer ${borrowerToken}` },
    data: { tool_id: tool.id, start_date: fmt(start), end_date: fmt(end) },
  });
  if (!resResponse.ok()) {
    throw new Error(`create reservation failed: ${resResponse.status()} ${await resResponse.text()}`);
  }
  const reservation = (await resResponse.json()) as { id: string };

  const approveResponse = await page.request.post(
    `/api/v1/reservations/${reservation.id}/approve`,
    { headers: { Authorization: `Bearer ${ownerToken}` } },
  );
  if (!approveResponse.ok()) {
    throw new Error(`approve failed: ${approveResponse.status()} ${await approveResponse.text()}`);
  }

  const pickupResponse = await page.request.post(
    `/api/v1/reservations/${reservation.id}/mark-picked-up`,
    { headers: { Authorization: `Bearer ${borrowerToken}` } },
  );
  if (!pickupResponse.ok()) {
    throw new Error(`mark-picked-up failed: ${pickupResponse.status()} ${await pickupResponse.text()}`);
  }

  return { toolId: tool.id, reservationId: reservation.id };
}

interface ReviewSummary {
  id: string;
  reviewer_id: string;
}

/**
 * Delete the logged-in user's own review of a reservation, if one exists.
 *
 * Tests that submit a fresh review share one backend with no per-test reset
 * (see the file header above), so a Playwright retry of the SAME test can
 * find its own prior attempt's review already sitting there -- the "Submit
 * Review" button it waits for has become "Update Review" and the test hangs
 * until timeout. Call this before submitting so the test is retry-safe
 * regardless of what an earlier attempt left behind.
 */
export async function clearOwnReview(page: Page, reservationId: string): Promise<void> {
  const me = await apiGet<{ id: string }>(page, '/api/v1/auth/me');
  const reviews = await apiGet<ReviewSummary[]>(
    page,
    `/api/v1/reservations/${reservationId}/review`,
  );
  const mine = reviews.find((review) => review.reviewer_id === me.id);
  if (mine) {
    await apiDelete(page, `/api/v1/reviews/${mine.id}`);
  }
}

/**
 * Look up a seeded reservation by its tool's name.
 *
 * Reservation IDs are real UUIDs assigned at seed time (scripts/seed_dev.py),
 * not the old mock's hardcoded 'reservation-1' style, so tests navigate by
 * looking the ID up via the API first. /tools only lists listings the
 * current user doesn't own (it's the browse/reserve view), so a tool the
 * logged-in user owns (e.g. seeded Hammer, owned by member02) is looked up
 * via /tools/me instead.
 */
export async function findReservationByToolName(
  page: Page,
  toolName: string,
): Promise<ReservationSummary> {
  const browse = await apiGet<PaginatedResult<ToolSummary>>(
    page,
    `/api/v1/tools?search=${encodeURIComponent(toolName)}&page_size=5`,
  );
  let tool = browse.items.find((t) => t.name === toolName);
  if (!tool) {
    const mine = await apiGet<PaginatedResult<ToolSummary>>(page, '/api/v1/tools/me?page_size=100');
    tool = mine.items.find((t) => t.name === toolName);
  }
  if (!tool) throw new Error(`Seeded tool "${toolName}" not found`);

  const reservations = await apiGet<PaginatedResult<ReservationSummary>>(
    page,
    '/api/v1/reservations?page_size=100',
  );
  const reservation = reservations.items.find((r) => r.tool_id === tool.id);
  if (!reservation) throw new Error(`No reservation found for tool "${toolName}"`);
  return reservation;
}

/** Look up a seeded tool's id by name (browse list, falling back to /tools/me). */
export async function getToolId(page: Page, toolName: string): Promise<string> {
  const browse = await apiGet<PaginatedResult<ToolSummary>>(
    page,
    `/api/v1/tools?search=${encodeURIComponent(toolName)}&page_size=5`,
  );
  const tool = browse.items.find((t) => t.name === toolName);
  if (tool) return tool.id;
  const mine = await apiGet<PaginatedResult<ToolSummary>>(page, '/api/v1/tools/me?page_size=100');
  const own = mine.items.find((t) => t.name === toolName);
  if (!own) throw new Error(`Seeded tool "${toolName}" not found`);
  return own.id;
}
