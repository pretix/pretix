cat > /Users/arushi_tewari/Desktop/pretix/tests/test-create-event.spec.ts << 'EOF'
import { test, expect, Page } from "@playwright/test";

const BASE_URL = process.env.PRETIX_BASE_URL ?? "http://localhost:8000";
const ADMIN_EMAIL = process.env.PRETIX_ADMIN_EMAIL ?? "arushi.tewari17@gmail.com";
const ADMIN_PASSWORD = process.env.PRETIX_ADMIN_PASSWORD ?? "pretix@123";
const TEST_EVENT_NAME = `Playwright Test Event ${Date.now()}`;
const TEST_EVENT_SLUG = `pw-${Date.now()}`;

async function loginAsAdmin(page: Page) {
  await page.goto(`${BASE_URL}/control/login`);
  await page.getByRole('textbox', { name: 'Email' }).fill(ADMIN_EMAIL);
  await page.getByRole('textbox', { name: 'Password' }).fill(ADMIN_PASSWORD);
  await page.getByRole('textbox', { name: 'Password' }).press('Enter');
  await page.waitForLoadState("networkidle");
}

test.describe("630:P1 - Create event and verify it appears in events list", () => {
  test.setTimeout(120_000);

  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("creates a new event and verifies it appears in the events list", async ({ page }) => {

    // Step 1: Navigate to create event form
    await page.getByRole('link', { name: /Events/ }).first().click();
    await page.waitForLoadState("networkidle");
    await page.getByRole('link', { name: /Create a new event/ }).click();
    await page.waitForLoadState("networkidle");

    // Step 2: Select event type and language → Continue
    await page.getByRole('radio', { name: /Singular event or non-event/ }).check();
    await page.getByRole('checkbox', { name: 'English' }).check();
    await page.getByRole('button', { name: 'Continue' }).click();
    await page.waitForLoadState("networkidle");

    // Step 3: Fill event details → Continue
    await page.getByPlaceholder('English', { exact: true }).fill(TEST_EVENT_NAME);
    await page.getByRole('textbox', { name: 'Short form Short form' }).fill(TEST_EVENT_SLUG);
    await page.getByRole('group', { name: 'Event start time' }).getByPlaceholder('-12-31').fill('2026-06-01');
    await page.getByRole('group', { name: 'Event start time' }).getByPlaceholder(':00:00').fill('09:00:00');
    await page.getByRole('group', { name: 'Event end time Optional' }).getByPlaceholder('-12-31').fill('2026-06-01');
    await page.getByRole('button', { name: 'Continue' }).click();
    await page.waitForLoadState("networkidle");

    // Step 4: Tax — skip → Continue
    await page.getByRole('checkbox', { name: "I don't want to specify taxes now" }).check();
    await page.getByRole('button', { name: 'Continue' }).click();
    await page.waitForLoadState("networkidle");

    // Step 5: Copy config (optional) — skip → Continue
    await page.getByRole('button', { name: 'Continue' }).click();
    await page.waitForLoadState("networkidle");

    // Step 6: Save
    await page.getByRole('button', { name: 'Save' }).click();
    await page.waitForLoadState("networkidle");

    // Step 7: Navigate to events list
    await page.goto(`${BASE_URL}/control/events/`);
    await page.waitForLoadState("networkidle");

    // Step 8: Verify event appears in list
    const eventEntry = page.locator(`text=${TEST_EVENT_NAME}`).first();
    await expect(eventEntry).toBeVisible({ timeout: 15_000 });
  });
});
EOF
