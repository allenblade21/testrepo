/**
 * 团购界面 /tuangou E2E（G-R3）。
 *
 * 覆盖：页面加载 + 数据源探针行、人数筛选、卡片展开触发 /compare、
 * 人均到手价与降级标注渲染、搜索过滤、Mock 标注在位。
 *
 * 运行前提：python -m uvicorn app.main:app --port 8077
 * 运行：node tests/e2e/tuangou.spec.mjs [chromium可执行文件路径]
 */
import { chromium } from 'playwright-core';

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8077';
const CHROME = process.argv[2] || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';

let failures = 0;
function check(cond, msg){
  console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${msg}`);
  if(!cond) failures++;
}

const browser = await chromium.launch({ executablePath: CHROME });
const page = await browser.newPage({ viewport: { width: 480, height: 900 } });
const errors = [];
page.on('pageerror', e => errors.push(e.message));

await page.goto(`${BASE}/tuangou`);
await page.waitForTimeout(700);

check((await page.locator('.mock').innerText()).includes('非真实价格'), 'Mock 标注在位');
check((await page.locator('#srcline').innerText()).includes('数据源'), '数据源探针行渲染');
const countAll = await page.locator('#count').innerText();
check(/命中 \d+ 个/.test(countAll), `全量列表渲染（${countAll}）`);

// 人数筛选：4 人 → 命中数应下降（Mock 种子里 2-2 档被排除）
await page.click('[data-p="4"]');
await page.waitForTimeout(400);
const count4 = await page.locator('#count').innerText();
check(count4.includes('适用 4 人'), `人数筛选生效（${count4}）`);

// 展开第一张卡 → POST /compare → 人均与详情渲染
await page.locator('.chead').first().click();
await page.waitForTimeout(600);
const percap = (await page.locator('.card.open .percap').first().innerText()).replace(/\s+/g, '');
check(/¥[\d.]+/.test(percap), `人均到手价渲染（${percap.slice(0, 12)}）`);
const platCount = await page.locator('.card.open .plat').count();
check(platCount >= 1, `平台块渲染（${platCount} 个）`);

// 降级标注：搜「烤串」（丰茂无菜品明细）展开应见「未含菜品明细」
await page.fill('#q', '烤串');
await page.waitForTimeout(500);
const countQ = await page.locator('#count').innerText();
check(/命中 [1-9]/.test(countQ), `搜索过滤生效（${countQ}）`);
await page.locator('.chead').first().click();
await page.waitForTimeout(600);
const detail = await page.locator('.card.open .detail').first().innerText();
check(detail.includes('未含菜品明细'), '菜品缺失降级标注在位');

check(errors.length === 0, `无页面 JS 错误（${errors.length}）`);

await browser.close();
console.log(failures ? `\n${failures} 项失败` : '\n全部通过');
process.exit(failures ? 1 : 0);
