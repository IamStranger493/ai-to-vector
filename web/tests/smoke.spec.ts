import { test, expect } from "@playwright/test";
import path from "path";

test.describe("Vectorizer Studio Web Smoke Test", () => {
  test("uploading a PNG renders non-zero image/canvas and enables panel scrolling", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(err.toString());
    });

    await page.goto("/");

    // Upload golden PNG
    const pngPath = path.resolve("..", "tests", "golden", "illustration.png");
    const fileInput = page.locator("#file-input");
    await fileInput.setInputFiles(pngPath);

    // Wait for image element to display
    const refImg = page.locator("#ref-image");
    await expect(refImg).toBeVisible();

    // Assert img/canvas has non-zero natural size and rendered size
    const imgMetrics = await refImg.evaluate((img: HTMLImageElement) => {
      const rect = img.getBoundingClientRect();
      return {
        naturalWidth: img.naturalWidth,
        naturalHeight: img.naturalHeight,
        renderedWidth: rect.width,
        renderedHeight: rect.height,
      };
    });

    expect(imgMetrics.naturalWidth).toBeGreaterThan(0);
    expect(imgMetrics.naturalHeight).toBeGreaterThan(0);
    expect(imgMetrics.renderedWidth).toBeGreaterThan(0);
    expect(imgMetrics.renderedHeight).toBeGreaterThan(0);

    // Assert canvas transform container has non-zero size
    const canvasTransform = page.locator("#canvas-transform");
    const transformMetrics = await canvasTransform.evaluate((el: HTMLElement) => {
      const rect = el.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    });
    expect(transformMetrics.width).toBeGreaterThan(0);
    expect(transformMetrics.height).toBeGreaterThan(0);

    // Assert params panel has scrollable content (scrollHeight > clientHeight)
    const paramsContainer = page.locator("#params-container");
    const scrollMetrics = await paramsContainer.evaluate((el: HTMLElement) => {
      return {
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        canScroll: el.scrollHeight > el.clientHeight,
      };
    });
    expect(scrollMetrics.canScroll).toBe(true);

    // Assert no JavaScript errors in console
    expect(consoleErrors).toEqual([]);
  });

  test("corrupted image shows visible error message in UI", async ({ page }) => {
    await page.goto("/");
    const fakeFile = {
      name: "corrupt.png",
      mimeType: "image/png",
      buffer: Buffer.from("CORRUPT_INVALID_HEADER_DATA"),
    };
    await page.locator("#file-input").setInputFiles(fakeFile);

    const errorBanner = page.locator("#upload-error-banner");
    await expect(errorBanner).toBeVisible();
    await expect(errorBanner).not.toHaveClass(/hidden/);
    const text = await errorBanner.textContent();
    expect(text).toContain("Failed to decode image");
  });
});
