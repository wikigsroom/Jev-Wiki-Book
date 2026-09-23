'use strict';
// Durable acceptance test in an isolated native Windows CI runner.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const { execFileSync } = require('node:child_process');
if (!process.env.CI) throw new Error('Run this acceptance test in the native Windows CI job.');
const { _electron, chromium } = require(process.env.JEV_PLAYWRIGHT_PACKAGE);
const desktop = path.resolve(__dirname, '..');
const root = fs.mkdtempSync(path.join(desktop, 'build', 'ui-smoke-'));
const output = path.join(desktop, 'build', 'ui-verification');
fs.mkdirSync(output, { recursive: true });
fs.symlinkSync(path.join(desktop, 'build', 'backend'), path.join(root, 'JEV-runtime'), 'junction');
fs.symlinkSync(path.resolve(process.env.JEV_TEST_MODELS), path.join(root, 'JEV-models'), 'junction');
fs.mkdirSync(path.join(root, 'JEV'));
fs.mkdirSync(path.join(root, 'other-documents'));
fs.writeFileSync(path.join(root, 'JEV', '借阅规则.md'), '资料室文档借阅期限为十四天。', 'utf8');
fs.writeFileSync(path.join(root, 'other-documents', '另一份规则.md'), '资料室文档借阅期限为二十一天。', 'utf8');
const env = { ...process.env, PORTABLE_EXECUTABLE_DIR: root };
delete env.ELECTRON_RUN_AS_NODE;
let electron, browser, page;
const errors = [];
async function launch() {
  const executableName = require('../package.json').build.productName + '.exe';
  electron = await _electron.launch({ executablePath: path.join(desktop, 'dist', 'win-unpacked', executableName), env, timeout: 120000 });
  page = await electron.firstWindow();
  page.on('pageerror', error => errors.push(String(error)));
  await page.waitForURL(/^http:\/\/127\.0\.0\.1:/, { timeout: 120000 });
  await page.getByRole('button', { name: '检索设置与运行状态', exact: true }).waitFor();
}
async function settings() { await page.getByRole('button', { name: '检索设置与运行状态', exact: true }).click(); }
async function freePort() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
async function noListener(url) {
  await assert.rejects(fetch(url + '/api/health', { signal: AbortSignal.timeout(3000) }));
}
async function search(tab, expected) {
  await tab.locator('#question').fill('资料室文档借阅期限是什么？');
  await tab.getByRole('button', { name: '查找原文' }).click();
  await tab.locator('blockquote').first().waitFor({ timeout: 180000 });
  assert.match(await tab.locator('blockquote').first().innerText(), new RegExp(expected));
}
(async () => {
  const port = await freePort();
  const url = `http://127.0.0.1:${port}`;
  try {
    await launch();
    const privateOrigin = new URL(page.url()).origin;
    assert.equal((await fetch(privateOrigin + '/api/config')).status, 403);
    let failed = false;
    await page.route('**/api/sharing', route => {
      if (!failed && route.request().method() === 'GET') {
        failed = true;
        return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"测试读取失败"}' });
      }
      return route.continue();
    });
    await settings();
    await page.getByRole('button', { name: '重新加载共享设置' }).click();
    await page.getByLabel('启用 Web 查询端').waitFor();
    assert.equal(await page.getByLabel('启用 Web 查询端').isChecked(), false);
    await page.getByLabel('启用 Web 查询端').check();
    await page.getByLabel('访问端口', { exact: true }).fill(String(port));
    await page.getByRole('button', { name: '应用查询端设置' }).click();
    await page.locator('.sharing-address').waitFor();
    assert.match(await page.locator('.sharing-address').innerText(), new RegExp(String(port)));
    await page.screenshot({ path: path.join(output, 'electron-sharing.png') });
    browser = await chromium.launch();
    const query = await browser.newPage();
    query.on('pageerror', error => errors.push(String(error)));
    await query.goto(url);
    assert.equal(await query.locator('#source, #libraries, input[type=file]').count(), 0);
    for (const route of ['/api/documents', '/api/config', '/api/source-root', '/api/admin/status']) {
      assert.equal((await fetch(url + route)).status, 404);
    }
    await search(query, '十四天');
    await page.getByRole('button', { name: '完成', exact: true }).click();
    await page.getByRole('button', { name: '切换目录', exact: true }).click();
    await page.locator('#source-path').fill(path.join(root, 'other-documents'));
    await page.getByRole('button', { name: '扫描并使用此目录' }).click();
    await page.locator('#source-path').waitFor({ state: 'hidden' });
    await page.waitForFunction(() => ![...document.querySelectorAll('button')].find(button => button.textContent.includes('切换目录'))?.disabled);
    await search(query, '二十一天');
    assert.doesNotMatch(await query.locator('#results').innerText(), /十四天/);
    await query.screenshot({ path: path.join(output, 'desktop-shared-query.png') });
    await electron.close(); electron = null;
    await noListener(url);
    await launch();
    await settings();
    assert.equal(await page.getByLabel('启用 Web 查询端').isChecked(), true);
    assert.equal((await fetch(url + '/api/health')).status, 200);
    await page.getByLabel('启用 Web 查询端').uncheck();
    await page.getByRole('button', { name: '应用查询端设置' }).click();
    await page.locator('.sharing-address').waitFor({ state: 'hidden' });
    await noListener(url);
    assert.deepEqual(errors, []);
    const report = { passed: true, default_disabled: true, initial_error_retry: true, enabled_via_settings: true,
      private_backend_protected: true, public_routes_restricted: true, real_cpu_original_evidence: true,
      source_switch_respected: true, restored_after_restart: true, disabled_via_settings: true,
      commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: desktop, encoding: 'utf8' }).trim() };
    fs.writeFileSync(path.join(output, 'electron-ui-verification.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally {
    if (browser) await browser.close();
    if (electron) await electron.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
