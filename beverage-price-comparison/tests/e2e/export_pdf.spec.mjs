/**
 * 导出比价结果 PDF · E2E（v0.7.0）。
 *
 * 覆盖：无记录时导出栏隐藏 → 比价多项后出现且计数正确 → 点击导出下载
 * 合法 PDF（%PDF-）→ /export 响应带时间戳文件名 → 清空后隐藏。
 *
 * 前置：服务已启动；npm i playwright-core。
 * 运行：node tests/e2e/export_pdf.spec.mjs [chrome路径]
 */
import { chromium } from 'playwright-core';
import fs from 'fs';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8077';
const CHROME = process.argv[2] || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const TMP = process.env.TMPDIR || '/tmp';

let fail = 0;
const ck = (c, m) => { console.log(`  ${c ? 'PASS' : 'FAIL'}  ${m}`); if (!c) fail++; };

const browser = await chromium.launch({ executablePath: CHROME });
const ctx = await browser.newContext({ viewport: { width: 900, height: 1200 }, acceptDownloads: true });
const p = await ctx.newPage();
const errs = [];
p.on('pageerror', e => errs.push(e.message));
await p.goto(BASE + '/', { waitUntil: 'networkidle' });

ck(await p.locator('#exportbar').isHidden(), '初始无记录时导出栏隐藏');

// 比价两个不同商品
await p.fill('#q', '可乐'); await p.waitForTimeout(400);
await p.locator('.unit').first().click(); await p.waitForSelector('.cmp');
await p.fill('#q', '农夫山泉'); await p.waitForTimeout(400);
await p.locator('.unit').first().click(); await p.waitForSelector('.cmp');
ck(!(await p.locator('#exportbar').isHidden()), '比价后导出栏出现');
ck((await p.locator('#exportcount').innerText()).includes('2 项'), '计数=2 项');

// 点导出：同时捕获 /export 网络响应（权威文件名）与下载
const [resp, dl] = await Promise.all([
  p.waitForResponse(r => r.url().endsWith('/export') && r.request().method() === 'POST'),
  p.waitForEvent('download'),
  p.click('#exportbtn'),
]);
ck(resp.status() === 200, `/export 返回 200`);
const cd = resp.headers()['content-disposition'] || '';
ck(/comparison_\d{8}_\d{6}\.pdf/.test(cd), `响应文件名带时间戳：${cd.slice(0, 60)}`);

const path = `${TMP}/e2e-export.pdf`;
await dl.saveAs(path);
const buf = fs.readFileSync(path);
ck(buf.subarray(0, 5).toString() === '%PDF-', '下载内容是合法 PDF');
ck(buf.length > 1500, `PDF 大小 ${buf.length} 字节`);
fs.unlinkSync(path);

// 清空后隐藏
await p.click('.clearbtn'); await p.waitForTimeout(200);
ck(await p.locator('#exportbar').isHidden(), '清空后导出栏隐藏');

ck(errs.length === 0, `无 JS 错误（${errs.length}）`);
await browser.close();
console.log(fail === 0 ? '\n全部通过 ✅' : `\n${fail} 项失败 ❌`);
process.exit(fail === 0 ? 0 : 1);
