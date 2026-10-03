const { chromium } = require("playwright");
const results = [];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const ok = (n, c) => { results.push(`${c ? "PASS" : "FAIL"} ${n}`); if (!c) process.exitCode = 1; };

  await page.goto("http://localhost:8080", { waitUntil: "networkidle" });

  // 1. 通过弹窗创建「辩论 · 苏格拉底 vs 休谟 · 自动连播」
  await page.getByRole("complementary").getByRole("button", { name: "新建会议" }).click();
  await page.waitForSelector("[role=dialog]");
  await page.fill("#topic", "AI 现在能玩好实时动作游戏么");
  await page.locator("[role=dialog] .cursor-pointer", { hasText: "辩论" }).click();
  await page.locator("#autoplay").click();
  await page.screenshot({ path: "../../shots/iv-1-dialog.png" });
  await page.getByRole("button", { name: "创建并进入会议" }).click();
  await page.waitForSelector("text=会议室已创建", { timeout: 15000 });
  await page.getByRole("button", { name: "继续" }).click();
  ok("创建会议并进入房间", true);

  // 2. 开启自动连播，观察正方流式 + 阶段标签
  await page.waitForSelector(".markdown-body", { timeout: 480000 });
  const len1 = (await page.locator(".markdown-body").last().textContent())?.length ?? 0;
  await page.waitForTimeout(700);
  const len2 = (await page.locator(".markdown-body").last().textContent())?.length ?? 0;
  ok(`正方流式输出（${len1}→${len2}）`, len2 > len1);
  const phaseHit = await page.locator("text=/整理思路|自我审视|输出最终发言|思考中|发言中/").count();
  ok("参与者状态可见", phaseHit > 0);

  // 3. 等反方发言
  await page.waitForFunction(
    () => document.body.innerText.includes("休谟") && document.querySelectorAll(".markdown-body").length >= 2,
    undefined,
    { timeout: 480000 },
  );
  ok("反方完成发言", true);

  // 4. 等裁判总结（VERDICT 卡片）
  await page.waitForSelector("text=裁判总结", { timeout: 480000 });
  const verdictText = (await page.locator("text=/裁判总结/").first().textContent()) ?? "";
  ok("裁判总结卡片出现", verdictText.includes("裁判总结"));
  const bubbleAll = (await page.locator(".markdown-body").allTextContents()).join("");
  ok("无 PHASE 标记泄漏", !bubbleAll.includes("[PHASE]"));
  ok("无调用失败", !bubbleAll.includes("调用失败") && !bubbleAll.includes("LLM 服务不可用"));
  await page.screenshot({ path: "../../shots/iv-2-verdict.png" });

  // 5. 插话（观seud粗质询），验证 Enter 发送
  await page.fill("footer textarea", "请问双方如何看待反应速度对游戏体验的决定性作用？");
  await page.press("footer textarea", "Enter");
  await page.waitForSelector("text=/反应速度对游戏体验/", { timeout: 15000 });
  ok("插话成功", true);
  await page.screenshot({ path: "../../shots/iv-3-interject.png" });

  // 6. 删除会议
  const card = page.locator("aside .cursor-pointer", { hasText: "AI 现在能玩好实时动作游戏么" }).first();
  await card.hover();
  await card.locator("button").last().click();
  await page.getByRole("menuitem", { name: "删除会议" }).click();
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await page.waitForFunction(
    () => !document.body.innerText.includes("AI 现在能玩好实时动作游戏么"),
    undefined,
    { timeout: 15000 },
  );
  ok("删除会议", true);

  console.log(results.join("\n"));
  await browser.close();
})().catch((e) => { console.log(results.join("\n")); console.log("ABORT:", e.message.slice(0, 200)); process.exit(1); });
