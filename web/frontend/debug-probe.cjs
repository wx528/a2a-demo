const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 150)); });
  page.on("pageerror", (e) => errors.push("PAGEERROR: " + String(e).slice(0, 150)));

  await page.goto("http://localhost:8080", { waitUntil: "networkidle" });
  await page.getByRole("complementary").getByRole("button", { name: "新建会议" }).click();
  await page.waitForSelector("[role=dialog]");
  await page.fill("#topic", "截图诊断流式");
  await page.locator("[role=dialog] .cursor-pointer", { hasText: "辩论" }).click();
  await page.getByRole("button", { name: "创建并进入会议" }).click();
  await page.waitForSelector("text=会议室已创建", { timeout: 15000 });
  await page.getByRole("button", { name: "继续" }).click();

  // 60 秒内每 5 秒采样一次 DOM
  for (let i = 0; i < 12; i++) {
    await page.waitForTimeout(5000);
    const md = await page.locator(".markdown-body").count();
    const text = (await page.evaluate(() => document.body.innerText)).slice(0, 0);
    const status = await page.evaluate(() => {
      const bar = [...document.querySelectorAll("div.border-b")].find((b) => b.textContent.includes("AGENTS"));
      return bar ? bar.textContent.slice(0, 120) : "no-bar";
    });
    console.log(`t=${(i + 1) * 5}s markdown-body=${md} | bar: ${status.replace(/\s+/g, " ")}`);
    if (md > 0) { await page.screenshot({ path: "../../shots/debug-stream.png" }); break; }
  }
  console.log("console errors:", JSON.stringify(errors.slice(0, 3)));
  await browser.close();
})().catch((e) => { console.log("ABORT:", e.message.slice(0, 200)); process.exit(1); });
