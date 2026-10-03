const { chromium } = require("playwright");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto("http://localhost:8080", { waitUntil: "networkidle" });

  await page.getByRole("complementary").getByRole("button", { name: "新建会议" }).click();
  await page.waitForSelector("[role=dialog]");
  await page.fill("#topic", "流式输出验证");
  await page.locator("[role=dialog] .cursor-pointer", { hasText: "辩论" }).click();
  await page.getByRole("button", { name: "创建并进入会议" }).click();
  await page.waitForSelector("text=会议室已创建", { timeout: 10000 });

  await page.getByRole("button", { name: "继续" }).click();

  // 等首个增量到达（占位气泡出现）
  await page.waitForSelector(".markdown-body", { timeout: 120000 });
  const len1 = (await page.locator(".markdown-body").last().textContent())?.length ?? 0;
  await page.waitForTimeout(600);
  const len2 = (await page.locator(".markdown-body").last().textContent())?.length ?? 0;
  console.log(`stream growth: ${len1} -> ${len2}`);
  if (len2 <= len1) console.log("WARN: no growth sampled (LLM may have finished fast)");
  await page.screenshot({ path: "../../shots/stream-mid.png" });

  // 等本轮结束：占位被正式消息替换，下一位发言者出现
  await page.waitForFunction(
    () => document.body.innerText.includes("下一位发言："),
    undefined,
    { timeout: 120000 },
  );
  const finalLen = (await page.locator(".markdown-body").last().textContent())?.length ?? 0;
  console.log(`final len: ${finalLen} (>= sampled ${len2})`);
  if (finalLen < len2) { console.log("FAIL: final message lost content"); process.exit(1); }
  console.log("STREAM SMOKE PASS");

  await page.evaluate(async () => {
    const list = await (await fetch("/api/meetings")).json();
    for (const m of list) if (m.topic === "流式输出验证") await fetch(`/api/meetings/${m.id}`, { method: "DELETE" });
  });
  await browser.close();
})().catch((e) => { console.log("ABORT:", e.message.slice(0, 200)); process.exit(1); });
