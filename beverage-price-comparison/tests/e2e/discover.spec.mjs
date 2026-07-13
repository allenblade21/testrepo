/**
 * 商户发现界面 /discover E2E（v0.6.0）。
 *
 * 覆盖：全部商户 + 商品分页(100)、翻页不重不漏、模糊搜商户、
 * 商户 chip 钻取、点商品内联比价、GPS 网格过滤+排名、手机无横向溢出。
 *
 * 前置：服务已在 127.0.0.1:8077 启动；npm i playwright-core。
 * 运行：node tests/e2e/discover.spec.mjs [chrome路径]
 */
import { chromium } from 'playwright-core';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8077';
const CHROME = process.argv[2] || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const WANGJING = { latitude: 39.9960, longitude: 116.4740 };

let fail = 0;
const ck = (c, m) => { console.log(`  ${c ? 'PASS' : 'FAIL'}  ${m}`); if (!c) fail++; };

const browser = await chromium.launch({ executablePath: CHROME });
const ctx = await browser.newContext({
  viewport: { width: 900, height: 1200 },
  geolocation: WANGJING, permissions: ['geolocation'],
});
const p = await ctx.newPage();
const errs = [];
p.on('pageerror', e => errs.push(e.message));
await p.goto(BASE + '/discover', { waitUntil: 'networkidle' });
await p.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
await p.reload({ waitUntil: 'networkidle' });

await p.waitForSelector('.mchip');
ck((await p.locator('.mchip').count()) >= 10, `初始商户 chips ≥10：${await p.locator('.mchip').count()}`);
ck((await p.locator('.pitem').count()) === 100, `首页商品 100：${await p.locator('.pitem').count()}`);
ck((await p.locator('#pager').innerText()).includes('116'), '分页器显示总数 116');

// 翻页 → 次页 16，且首页/次页无重复
const idsPage1 = await p.$$eval('.pitem', els => els.map(e => e.id));
await p.click('.pgbtn:has-text("下一页")');
await p.waitForTimeout(400);
ck((await p.locator('.pitem').count()) === 16, `次页商品 16：${await p.locator('.pitem').count()}`);
const idsPage2 = await p.$$eval('.pitem', els => els.map(e => e.id));
ck(!idsPage1.some(id => idsPage2.includes(id)), '翻页无重复商品');

// 模糊搜商户
await p.fill('#mq', '便利');
await p.waitForTimeout(450);
ck((await p.locator('.mchip').count()) === 2, `模糊「便利」→2 商户：${await p.locator('.mchip').count()}`);

// 商户 chip 钻取
await p.locator('.mchip').first().click();
await p.waitForTimeout(400);
ck((await p.locator('.mchip.all').count()) === 1, '钻取后出现「返回全部」');

// 点商品 → 内联比价
await p.locator('.pitem').first().click();
await p.waitForSelector('.cmp');
ck((await p.locator('.col.best').count()) === 1, '点商品→出现比价最优卡');

// GPS 网格过滤 + 排名
await p.fill('#mq', '');
await p.waitForTimeout(400);
await p.locator('.gridchip', { hasText: '望京' }).click();
await p.waitForTimeout(500);
ck((await p.locator('.mchip .rk').count()) > 0, '望京网格下商户显示排名分');

ck(errs.length === 0, `无 JS 错误（${errs.length}）`);
await ctx.close();

// 手机无横向溢出
const m = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
await m.goto(BASE + '/discover', { waitUntil: 'networkidle' });
await m.waitForTimeout(600);
const ov = await m.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
ck(ov <= 1, `手机 390px 无横向溢出（${ov}px）`);

await browser.close();
console.log(fail === 0 ? '\n全部通过 ✅' : `\n${fail} 项失败 ❌`);
process.exit(fail === 0 ? 0 : 1);
