const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const net = [];
  page.on("response", (r) => { if (r.request().method() === "DELETE") net.push(`${r.status()} ${r.url()}`); });
  page.on("console", (m) => { if (m.type() === "error") console.log("CONSOLE-ERR:", m.text().slice(0, 150)); });

  await page.goto("http://localhost:8080", { waitUntil: "networkidle" });
  const created = await page.evaluate(async () => {
    const r = await fetch("/api/meetings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: "删除调试专用", mode: "pipeline", max_rounds: 1, auto_play: false }),
    });
    return r.json();
  });
  await page.reload({ waitUntil: "networkidle" });

  const card = page.locator("aside .cursor-pointer", { hasText: "删除调试专用" }).first();
  await card.hover();
  await card.locator("button").last().click();
  await page.getByRole("menuitem", { name: "删除会议" }).click();
  await page.waitForSelector("[role=alertdialog]", { timeout: 5000 });
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.waitForTimeout(2500);
  console.log("network:", net);
  const remaining = await page.locator("aside .cursor-pointer", { hasText: "删除调试专用" }).count();
  console.log("remaining cards:", remaining);
  await page.screenshot({ path: "../../shots/delete-debug.png" });

  await page.evaluate(async (id) => { await fetch(`/api/meetings/${id}`, { method: "DELETE" }); }, created.id);
  await browser.close();
})().catch((e) => { console.log("ABORT:", e.message.slice(0, 200)); process.exit(1); });
