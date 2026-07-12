/**
 * 「加载更多」分页计数 E2E 回归测试（BUG-003）。
 *
 * BUG-003：追加加载错误读取输入框实时值作为查询词——
 * 「输入新词 → 防抖(250ms)未触发 → 点加载更多」会以 新词+旧偏移 请求，
 * 覆盖 curTotal 后出现「已显示 40 / 共 32」的数字错乱。
 * 修复：追加请求钉死在列表所属查询词 curQuery 上。
 *
 * 运行前提：
 *   1. 服务已启动：python -m uvicorn app.main:app --port 8077
 *   2. npm install playwright-core（Chromium 使用 /opt/pw-browsers 预装或本机路径）
 * 运行：node tests/e2e/load_more.spec.mjs [chromium可执行文件路径]
 * 退出码 0=全部通过，1=有失败。
 */
import { chromium } from 'playwright-core';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8077';
const CHROME = process.argv[2] || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

let failures = 0;
function check(cond, msg){
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${msg}`);
  if(!cond) failures++;
}

/** 对账不变式：DOM卡片数 == 「已显示N」 && 「还有X」== 共−已显示 && 无重复卡片 */
async function audit(page, tag){
  const s = await page.evaluate(() => {
    const ids = Array.from(document.querySelectorAll('.unit')).map(c => c.id);
    const dups = ids.filter((v, i) => ids.indexOf(v) !== i).length;
    return { n: ids.length, dups,
             meta: document.getElementById('meta').textContent,
             more: document.getElementById('more').textContent };
  });
  const shown = +((s.meta.match(/已显示 (\d+)/) || [])[1] || 0);
  const total = +((s.meta.match(/共 (\d+)/) || [])[1] || 0);
  const left  = +((s.more.match(/还有 (\d+)/) || [])[1] || 0);
  const consistent = shown === s.n && total - shown === left && s.dups === 0 && shown <= total;
  check(consistent, `${tag}: DOM=${s.n} 已显示=${shown} 共=${total} 还有=${left} 重复=${s.dups}`);
  return { shown, total, left, n: s.n };
}

const browser = await chromium.launch({ executablePath: CHROME });
const page = await browser.newPage({ viewport: { width: 900, height: 1000 } });
const jsErrors = [];
page.on('pageerror', e => jsErrors.push(e.message));
await page.goto(BASE + '/', { waitUntil: 'networkidle' });
await page.waitForSelector('.unit');

console.log('用例1：带关键词逐页加载到底，每一步数字对账');
await page.locator('#q').pressSequentially('茶', { delay: 20 });
await page.waitForTimeout(500);
let st = await audit(page, '搜索"茶"首页');
let guard = 0;
while (st.left > 0 && guard++ < 10) {
  await page.click('.morebtn');
  await page.waitForTimeout(400);
  st = await audit(page, `加载第${guard + 1}页`);
}
check(st.shown === st.total, `到底后 已显示(${st.shown}) == 共(${st.total})`);
check(await page.locator('.morebtn').count() === 0, '到底后加载按钮消失');

console.log('用例2：快速连点加载更多，计数不乱、无重复卡片');
await page.fill('#q', 'x'); await page.waitForTimeout(350);
await page.fill('#q', '');  await page.waitForTimeout(500);
await audit(page, '重置浏览全库');
await Promise.all([
  page.click('.morebtn'),
  page.click('.morebtn').catch(() => {}),
  page.click('.morebtn').catch(() => {}),
]);
await page.waitForTimeout(900);
await audit(page, '连点3次后');

console.log('用例3（BUG-003 回归）：输入新词后防抖窗口内点加载更多');
await page.fill('#q', 'x'); await page.waitForTimeout(350);
await page.fill('#q', '');  await page.waitForTimeout(500);
await page.click('.morebtn'); await page.waitForTimeout(400);
const before = await audit(page, '浏览已加载2页');
// 触发竞态：写入新词并派发 input（防抖开始计时），立即点加载更多
await page.evaluate(() => {
  const el = document.getElementById('q');
  el.value = '茶';
  el.dispatchEvent(new Event('input', { bubbles: true }));
});
await page.click('.morebtn');           // ← 250ms 防抖窗口内
await page.waitForTimeout(120);
const racing = await audit(page, '竞态窗口内（修复点）');
check(racing.shown === before.shown + 20 && racing.total === before.total,
      `竞态中追加沿用旧查询：已显示 ${before.shown}→${racing.shown}，共 保持${racing.total}`);
await page.waitForTimeout(700);
const settled = await audit(page, '防抖结算后（切换到新词）');
check(settled.total === 32 && settled.shown === 20, '结算后正确切到"茶"(共32 显示20)');

check(jsErrors.length === 0, `无 JS 错误（${jsErrors.length}）`);
await browser.close();
console.log(failures === 0 ? '\n全部通过 ✅' : `\n${failures} 项失败 ❌`);
process.exit(failures === 0 ? 0 : 1);
