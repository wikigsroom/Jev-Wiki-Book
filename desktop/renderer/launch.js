'use strict';
function render(status) {
  document.getElementById('title').textContent = status.state === 'failed' ? '启动遇到了问题。' : '准备你的文档工作台。';
  document.getElementById('message').textContent = status.message;
  document.getElementById('progress').hidden = status.state === 'failed';
  document.getElementById('actions').hidden = status.state !== 'failed';
  document.getElementById('location').textContent = status.dataPath ? '数据目录：' + status.dataPath : '';
}
window.jevDesktop.onStatus(render);
window.jevDesktop.status().then(render);
document.getElementById('retry').addEventListener('click', () => window.jevDesktop.retry());
document.getElementById('logs').addEventListener('click', () => window.jevDesktop.openData());
document.getElementById('quit').addEventListener('click', () => window.jevDesktop.quit());
