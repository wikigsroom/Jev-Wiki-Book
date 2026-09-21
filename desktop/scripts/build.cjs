'use strict';
const { spawn } = require('node:child_process');
const path = require('node:path');
// Level 3 avoids spending many minutes recompressing the large ML runtime.
// Model weights are sidecar files and are never transformed by this build.
const child = spawn(process.execPath, [require.resolve('electron-builder/out/cli/cli.js'), '--win', 'portable', '--x64', '--publish', 'never', ...process.argv.slice(2)], {
  cwd: path.resolve(__dirname, '..'), stdio: 'inherit', windowsHide: true,
  env: { ...process.env, ELECTRON_BUILDER_COMPRESSION_LEVEL: process.env.ELECTRON_BUILDER_COMPRESSION_LEVEL || '3' }
});
child.on('error', error => { console.error(error.message); process.exitCode = 1; });
child.on('exit', code => { process.exitCode = code ?? 1; });
