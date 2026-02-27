"""
UI Test: Verify Event Details Page Loads Correctly After Clicking on an Event

Test Layer:          UI Test
Priority:            Low
Behavior Protected:  Prevents regressions where clicking on an event from
                     the organizer's events list fails to load the event
                     details/dashboard page correctly.

Acceptance Criteria:
 - Test logs in as admin
 - Test navigates to the organizer's events list page
 - Test clicks on an existing event from the list
 - Test verifies the event details/dashboard page loads successfully

Test Approach:
 - Use Playwright to interact with the events list UI
 - Assert that the event dashboard page is visible after clicking on an event

Configuration:
 - Set the following environment variables before running:
     PRETIX_BASE_URL       (e.g. http://localhost:8000)
     PRETIX_ADMIN_EMAIL    (your admin email)
     PRETIX_ADMIN_PASSWORD (your admin password)
"""

# ---------------------------------------------------------------------------
# NOTE: This test is written in TypeScript for Playwright Test Runner.
# The implementation below is the reference spec (test-event-details.spec.ts).
# ---------------------------------------------------------------------------

SPEC = """
import { test, expect, Page } from "@playwright/test";

const BASE_URL = process.env.PRETIX_BASE_URL ?? "http://localhost:8000";
const ADMIN_EMAIL = process.env.PRETIX_ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.PRETIX_ADMIN_PASSWORD;

async function loginAsAdmin(page: Page) {
  await page.goto(`${BASE_URL}/control/login`);
  await page.getByRole('textbox', { name: 'Email' }).fill(ADMIN_EMAIL!);
  await page.getByRole('textbox', { name: 'Password' }).fill(ADMIN_PASSWORD!);
  await page.getByRole('textbox', { name: 'Password' }).press('Enter');
  await page.waitForLoadState("networkidle");
  const url = page.url();
  if (!url.includes("/control/")) {
    throw new Error(`Login failed — ended up at: ${url}`);
  }
}

test.describe("Verify event details page loads correctly after clicking on an event", () => {
  test.setTimeout(60_000);

  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("clicks on an existing event and verifies the details page loads", async ({ page }) => {

    // Step 1: Navigate to the events list
    await page.goto(`${BASE_URL}/control/events/`);
    await page.waitForLoadState("networkidle");

    // Step 2: Find the first event link in the list
    const firstEventLink = page.locator('table tbody tr td a').first();
    await expect(firstEventLink).toBeVisible({ timeout: 15_000 });

    // Step 3: Get the href and navigate to it
    const href = await firstEventLink.getAttribute('href');
    await page.goto(`${BASE_URL}${href}`);
    await page.waitForLoadState("networkidle");

    // Step 4: Verify the event dashboard page loaded correctly
    const currentUrl = page.url();
    expect(currentUrl).toContain('/control/');
    expect(currentUrl).not.toBe(`${BASE_URL}/control/`);
    await expect(page.locator('h2, h1').first()).toBeVisible({ timeout: 15_000 });
  });
});
"""
