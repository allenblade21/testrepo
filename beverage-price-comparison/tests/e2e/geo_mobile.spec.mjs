/**
 * 定位 UI 移动/平板 Chrome 适配 E2E（v0.5.2）。
 *
 * 覆盖：
 *  1. iPhone / iPad Chrome 设备仿真下位置面板可开、商圈 chip 可点、
 *     授权定位可解析、无横向溢出、触控目标达标；
 *  2. 嵌入（iframe）场景：GPS 点击给出「内嵌页禁止定位」准确指引，
 *     不静默卡死（对应 Artifact 内嵌无法弹权限窗的真实限制）。
 *
 * 前置：服务已在 127.0.0.1:8077 启动；npm i playwright-core。
 * 运行：node tests/e2e/geo_mobile.spec.mjs [chrome路径]
 * 退出码 0=全过 1=有失败。
 */
import { chromium } from 'playwright-core';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8077';
const CHROME = process.argv[2] || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const WANGJING = { latitude: 39.9960, longitude: 116.4740 };

let fail = 0;
const ck = (c, m) => { console.log(`  ${c ? 'PASS' : 'FAIL'}  ${m}`); if (!c) fail++; };

const DEVICES = [
  { name: 'iPhone(390)', width: 390, height: 844, dpr: 3 },
  { name: 'iPad(768)', width: 768, height: 1024, dpr: 2 },
  { name: 'iPad landscape(1024)', width: 1024, height: 768, dpr: 2 },
];

const browser = await chromium.launch({ executablePath: CHROME });

// ---- 1. 各设备：授权定位 + 触控 + 无溢出 ----
for (const d of DEVICES) {
  console.log(`设备 ${d.name}：`);
  const ctx = await browser.newContext({
    viewport: { width: d.width, height: d.height },
    deviceScaleFactor: d.dpr,
    hasTouch: true,
    isMobile: d.width < 800,
    userAgent: 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120 Mobile',
    geolocation: WANGJING,
    permissions: ['geolocation'],
  });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  await p.goto(BASE + '/', { waitUntil: 'networkidle' });
  await p.evaluate(() => localStorage.clear());
  await p.reload({ waitUntil: 'networkidle' });

  // 面板通过点击（触屏用 tap）打开
  await p.tap('#locpill');
  ck(await p.locator('#locpanel').isVisible(), '位置面板可展开');

  // 触控目标 ≥40px（GPS 按钮与商圈 chip）
  const gpsBox = await p.locator('#gpsbtn').boundingBox();
  ck(gpsBox && gpsBox.height >= 40, `GPS 按钮触控高度 ${Math.round(gpsBox?.height)}px ≥40`);
  const chipBox = await p.locator('.gridchip').nth(1).boundingBox();
  ck(chipBox && chipBox.height >= 36, `商圈 chip 触控高度 ${Math.round(chipBox?.height)}px ≥36`);

  // 授权定位（Playwright 注入坐标，绕过真实弹窗）→ 解析望京
  await p.tap('#gpsbtn');
  await p.waitForFunction(
    () => document.getElementById('locpill').textContent.indexOf('望京') >= 0,
    { timeout: 8000 });
  ck(true, '授权定位→解析望京商圈');

  // 无横向溢出
  const ov = await p.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  ck(ov <= 1, `无横向溢出（${ov}px）`);

  // 手动切商圈也可点（tap 五道口）
  await p.tap('#locpill');
  await p.locator('.gridchip', { hasText: '五道口' }).tap();
  await p.waitForFunction(
    () => document.getElementById('locpill').textContent.indexOf('五道口') >= 0,
    { timeout: 5000 });
  ck(true, '触控手动切换商圈生效');

  ck(errs.length === 0, `无 JS 错误（${errs.length}）`);
  await ctx.close();
}

// ---- 2. 嵌入（iframe）场景：GPS 给出内嵌禁止定位的准确指引 ----
console.log('嵌入 iframe 场景：');
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true,
    // 故意不授予 geolocation，且不带 allow → 模拟内嵌被 Permissions Policy 拦截
  });
  const p = await ctx.newPage();
  // 用一个不带 allow="geolocation" 的 iframe 包裹应用页
  await p.setContent(
    `<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
     <iframe src="${BASE}/" style="width:100%;height:800px;border:0"></iframe>`,
    { waitUntil: 'networkidle' });
  const frame = p.frames().find(f => f.url().startsWith(BASE));
  ck(!!frame, 'iframe 内嵌应用页加载');
  await frame.click('#locpill');
  await frame.click('#gpsbtn');
  await frame.waitForFunction(
    () => document.getElementById('locmsg').textContent.indexOf('内嵌') >= 0
       || document.getElementById('locmsg').textContent.indexOf('嵌入') >= 0,
    { timeout: 6000 });
  const msg = await frame.locator('#locmsg').innerText();
  ck(msg.indexOf('嵌入') >= 0 || msg.indexOf('内嵌') >= 0, '内嵌态给出准确指引: ' + msg.slice(0, 28) + '…');
  // 内嵌下手动选商圈仍可用（降级路径）
  await frame.locator('.gridchip', { hasText: '国贸' }).click();
  await frame.waitForFunction(
    () => document.getElementById('locpill').textContent.indexOf('国贸') >= 0,
    { timeout: 5000 });
  ck(true, '内嵌态手动选商圈降级可用');
  await ctx.close();
}

await browser.close();
console.log(fail === 0 ? '\n全部通过 ✅' : `\n${fail} 项失败 ❌`);
process.exit(fail === 0 ? 0 : 1);
