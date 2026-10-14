import { expect, test } from "@playwright/test";

const shots = process.env.E2E_SCREENSHOT_DIR;

/**
 * The milestone-1 vertical slice, driven through the UI:
 * create project from a template -> real native KiCad project -> KiCad netlist,
 * ERC and DRC results displayed -> export -> download.
 */
test("vertical slice: template to validated KiCad project and download", async ({ page }) => {
  const name = `E2E blinker ${Date.now()}`;
  await page.goto("/");
  await page.getByTestId("new-project").click();
  await page.getByTestId("project-name-input").fill(name);
  await page.getByTestId("template-ne555_blinker").click();
  await page.getByTestId("create-project-submit").click();

  await expect(page).toHaveURL(/\/projects\//);
  await expect(page.getByTestId("symbol-U1")).toBeVisible();
  await expect(page.getByTestId("validation-badge").first()).toHaveAttribute("data-level", "preview");
  if (shots) await page.screenshot({ path: `${shots}/1-schematic.png` });

  // interactive schematic: select a component and see it in the inspector
  await page.getByTestId("symbol-R1").locator("g").first().click({ force: true });
  await expect(page.getByTestId("component-inspector")).toContainText("R1");

  // PCB view with real footprints and preview ratsnest
  await page.getByTestId("view-pcb").click();
  await expect(page.getByTestId("footprint-U1")).toBeVisible();
  if (shots) await page.screenshot({ path: `${shots}/2-pcb.png` });

  // Run the real KiCad checks
  await page.getByTestId("top-validate").click();
  await expect(page.getByTestId("check-netlist_match")).toHaveAttribute("data-status", "passed", { timeout: 150_000 });
  await expect(page.getByTestId("check-kicad_project")).toHaveAttribute("data-status", "passed");
  await expect(page.getByTestId("check-drc")).toHaveAttribute("data-status", "failed"); // unrouted board
  await expect(page.getByTestId("validation-badge").first()).toHaveAttribute("data-level", "structural");
  await page.getByTestId("check-drc").locator("button").first().click();
  if (shots) await page.screenshot({ path: `${shots}/3-validation.png` });

  // Export and download the native project
  await page.getByTestId("run-export").click();
  const link = page.getByTestId("artifact-gerbers_zip");
  await expect(link).toBeVisible({ timeout: 150_000 });
  const projectLink = page.getByTestId("artifact-kicad_project").first();
  const download = page.waitForEvent("download");
  await projectLink.click();
  const file = await download;
  expect(file.suggestedFilename()).toMatch(/-kicad\.zip$/);

  // 3D preview renders
  await page.getByTestId("view-3d").click();
  await expect(page.getByTestId("board-3d").locator("canvas")).toBeVisible();
  if (shots) await page.screenshot({ path: `${shots}/4-3d.png` });
});

test("dashboard rename and delete with confirmation", async ({ page }) => {
  const name = `E2E temp ${Date.now()}`;
  await page.goto("/");
  await page.getByTestId("new-project").click();
  await page.getByTestId("project-name-input").fill(name);
  await page.getByTestId("create-project-submit").click();
  await expect(page).toHaveURL(/\/projects\//);
  await page.goto("/");
  const card = page.getByTestId("project-card").filter({ hasText: name });
  await card.getByTestId("project-menu").click();
  await page.getByTestId("project-delete").click();
  await expect(page.getByTestId("confirm-delete")).toBeDisabled();
  await page.getByTestId("delete-confirm-input").fill(name);
  await page.getByTestId("confirm-delete").click();
  await expect(page.getByTestId("project-card").filter({ hasText: name })).toHaveCount(0);
});
