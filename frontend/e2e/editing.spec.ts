import { expect, test, type Page } from "@playwright/test";

async function center(page: Page, testId: string) {
  const box = await page.getByTestId(testId).first().boundingBox();
  if (!box) throw new Error(`no bounding box for ${testId}`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

test("place parts, connect pins, undo/redo", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("new-project").click();
  await page.getByTestId("project-name-input").fill(`E2E editing ${Date.now()}`);
  await page.getByTestId("create-project-submit").click();
  await expect(page).toHaveURL(/\/projects\//);

  const canvas = page.getByTestId("schematic-canvas");
  const box = (await canvas.boundingBox())!;
  await page.getByTestId("place-resistor_0805").click();
  await page.mouse.click(box.x + box.width * 0.35, box.y + box.height * 0.5);
  await expect(page.getByTestId("symbol-R1")).toBeVisible();
  await page.getByTestId("place-led_0805").click();
  await page.mouse.click(box.x + box.width * 0.65, box.y + box.height * 0.5);
  await expect(page.getByTestId("symbol-D1")).toBeVisible();

  // connect R1 pin 2 to D1 pin 2 (anode) with the connect tool
  await page.getByTestId("tool-wire").click();
  let p = await center(page, "pin-R1.2");
  await page.mouse.click(p.x, p.y);
  p = await center(page, "pin-D1.2");
  await page.mouse.click(p.x, p.y);
  await page.getByTestId("left-tab-nets").click();
  await expect(page.getByTestId("net-row-N_R1_2")).toBeVisible();

  // undo removes the connection again, redo restores it
  await page.getByTestId("undo").click();
  await expect(page.getByTestId("net-row-N_R1_2")).toHaveCount(0);
  await page.getByTestId("redo").click();
  await expect(page.getByTestId("net-row-N_R1_2")).toBeVisible();
});

test("route a PCB track between two pads of the same net", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("new-project").click();
  await page.getByTestId("project-name-input").fill(`E2E routing ${Date.now()}`);
  await page.getByTestId("template-led_indicator").click();
  await page.getByTestId("create-project-submit").click();
  await expect(page).toHaveURL(/\/projects\//);
  await page.getByTestId("view-pcb").click();
  await expect(page.getByTestId("footprint-R1")).toBeVisible();

  await page.getByTestId("tool-track").click();
  const a = await center(page, "pad-R1.2");
  const b = await center(page, "pad-D1.2");
  await page.mouse.click(a.x, a.y);
  await page.mouse.click(b.x, a.y); // horizontal corner
  await page.mouse.click(b.x, b.y); // ends on the pad of the same net -> track committed
  await page.getByTestId("right-tab-inspector").click();
  await expect(page.getByText("Tracks / vias").locator("..")).toContainText(/[1-9]\d* \/ 0/);
});
