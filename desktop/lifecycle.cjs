'use strict';
const path = require('node:path');

function portablePaths({ executable, portableDir, packaged, projectDir }) {
  const root = path.resolve(portableDir || (packaged ? path.dirname(executable) : path.join(projectDir, 'build', 'dev-portable')));
  return { root, data: path.join(root, 'JEV-data'), source: path.join(root, 'JEV'), models: packaged ? path.join(root, 'JEV-models') : path.resolve(projectDir, '..', 'models') };
}
function sameOrigin(value, origin) {
  try { return Boolean(origin) && new URL(value).origin === origin; } catch { return false; }
}
function isLauncher(value) {
  try { const u = new URL(value); return u.protocol === 'jev-app:' && u.hostname === 'desktop' && u.pathname === '/launch.html'; } catch { return false; }
}
function readiness(line) {
  if (!line.startsWith('JEV_READY ')) return null;
  const value = JSON.parse(line.slice(10));
  if (!Number.isInteger(value.port) || value.port < 1024 || value.port > 65535 || !Number.isInteger(value.pid) || value.pid < 1) throw new Error('Invalid backend readiness message');
  return value;
}
module.exports = { portablePaths, sameOrigin, isLauncher, readiness };
