"""
UI Test: Verify that the Search/Filter on the Events List Page Works Correctly

Test Layer:          UI Test
Priority:            Low
Behavior Protected:  Prevents regressions where the search functionality on
                     the events list page breaks and returns incorrect results.

Acceptance Criteria:
 - Test logs in as admin
 - Test navigates to the events list page
 - Test types an event name into the Event name filter
 - Test clicks the Filter button
 - Test verifies that the filtered results match the search query

Test Approach:
 - Use Playwright to interact with the search/filter bar on the events list page
 - Assert that the results shown match the searched term

Configuration:
 - Set the following environment variables before running:
     PRETIX_BASE_URL       (e.g. http://localhost:8000)
     PRETIX_ADMIN_EMAIL    (your admin email)
     PRETIX_ADMIN_PASSWORD (your admin password)
"""

# ---------------------------------------------------------------------------
# NOTE: This test is written in TypeScript for Playwright Test Runner.
# The implementation below is the reference spec (test-events-search.spec.ts).
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
  await page.getByRole('button', { name: 'Log in' }).click();
  await page.waitForLoadState("networkidle");
  const url = page.url();
  if (!url.includes("/control/")) {
    throw new Error(`Login failed — ended up at: ${url}`);
  }
}

test.describe("Verify search bar filters events correctly on the events list page", () => {
  test.setTimeout(60_000);

  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("search bar filters events by name", async ({ page }) => {

    // Step 1: Navigate to the events list page
    await page.goto(`${BASE_URL}/control/events/`);
    await page.waitForLoadState("networkidle");

    // Step 2: Grab the name of the first event in the list
    const firstEventName = await page.locator('table tbody tr td a').first().innerText();
    const searchTerm = firstEventName.trim().split(' ')[0];

    // Step 3: Fill in the Event name filter input
    await page.getByRole('textbox', { name: 'Event name' }).click();
    await page.getByRole('textbox', { name: 'Event name' }).fill(searchTerm);

    // Step 4: Click the Filter button
    await page.getByRole('button', { name: /Filter/ }).click();
    await page.waitForLoadState("networkidle");

    // Step 5: Verify results contain the search term
    const resultRows = page.locator('table tbody tr');
    const rowCount = await resultRows.count();
    expect(rowCount).toBeGreaterThan(0);

    const firstResult = await page.locator('table tbody tr td a').first().innerText();
    expect(firstResult.toLowerCase()).toContain(searchTerm.toLowerCase());
  });
});
"""
