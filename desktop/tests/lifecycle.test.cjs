const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { portablePaths, sameOrigin, isLauncher, readiness } = require('../lifecycle.cjs');

test('portable data and model paths follow the outer executable, never its extraction directory', () => {
  const root = path.resolve('build', '中文 便携目录');
  const result = portablePaths({ executable: path.resolve('build', 'temporary', 'JevDocumentSearchDesktop.exe'), portableDir: root, packaged: true });
  assert.equal(result.data, path.join(root, 'JEV-data'));
  assert.equal(result.source, path.join(root, 'JEV'));
  assert.equal(result.models, path.join(root, 'JEV-models'));
});
test('origin checks reject prefix tricks, different ports and file links', () => {
  const origin = 'http://127.0.0.1:54321';
  assert.ok(sameOrigin(origin + '/api/config', origin));
  for (const value of ['http://127.0.0.1:5432/', 'http://127.0.0.1:54321@example.com/', 'file:///test', 'http://127.0.0.1.evil.test:54321/', 'garbage']) assert.equal(sameOrigin(value, origin), false);
  assert.ok(isLauncher('jev-app://desktop/launch.html'));
  assert.equal(isLauncher('jev-app://desktop/other.html'), false);
});
test('readiness ignores ordinary logs and validates the selected port and child identity', () => {
  assert.equal(readiness('loading weights'), null);
  assert.deepEqual(readiness('JEV_READY {"port":45678,"pid":123}'), { port: 45678, pid: 123 });
  assert.throws(() => readiness('JEV_READY {"port":0,"pid":123}'));
  assert.throws(() => readiness('JEV_READY {"port":45678,"pid":0}'));
});
