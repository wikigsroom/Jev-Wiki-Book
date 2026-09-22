let session = null, libraries = [], poll = null, completedJob = null, scanning = false;
const $ = selector => document.querySelector(selector);
const notice = (message, error = false) => { $('#notice').hidden = !message; $('#notice').textContent = message; $('#notice').classList.toggle('error', error); };
async function api(route, data) {
  const response = await fetch('/api/admin/' + route, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session?.csrf_token || ''},body:JSON.stringify(data)});
  const body = await response.json();
  if (!response.ok) { if (response.status === 401 && route !== 'login') showLogin(); throw new Error(typeof body.detail === 'string' ? body.detail : '请检查输入内容后重试。'); }
  return body;
}
function showLogin() { session = null; clearInterval(poll); $('#login-panel').hidden = false; $('#dashboard').hidden = true; $('#password-panel').hidden = true; $('#account').hidden = true; $('#libraries').replaceChildren(); }
function showPassword() { clearInterval(poll); $('#dashboard').hidden = true; $('#password-panel').hidden = false; $('#cancel-password').hidden = session.must_change; $('#password-help').textContent = session.must_change ? '首次登录需要修改默认密码，完成后才能开放资料。新密码至少 12 个字符。' : '修改密码会使其他登录会话退出。新密码至少 12 个字符。'; $('#current-password').focus(); }
async function signedIn(value) { session = value; $('#login-panel').hidden = true; $('#account').hidden = false; if (value.must_change) showPassword(); else { $('#password-panel').hidden = true; $('#dashboard').hidden = false; await refresh(); clearInterval(poll); poll = setInterval(updateStatus, 2000); } }
function el(tag, text, cls) { const node = document.createElement(tag); node.textContent = text; if (cls) node.className = cls; return node; }
async function refresh() {
  const data = await api('libraries'); libraries = data.libraries; $('#libraries').replaceChildren();
  const count = data.publication.grants.reduce((total, grant) => total + grant.document_ids.length, 0);
  for (const library of libraries) {
    const group = el('section', '', 'library-group');
    group.append(el('h3', library.path));
    const grant = data.publication.grants.find(g => g.library_id === library.id);
    const selected = new Set(grant?.document_ids || []);
    if (grant && grant.generation !== library.generation) group.append(el('p', '此目录已重新扫描。查询端仍使用上次开放的版本；保存访问范围后才会开放本次内容。', 'help'));
    if (library.documents.length) {
      const allLabel = el('label', '', 'doc-row'); const all = document.createElement('input'); all.type = 'checkbox';
      allLabel.append(all, el('span', '选择此目录的全部已索引文档')); group.append(allLabel);
      for (const doc of library.documents) {
        const label = el('label', '', 'doc-row'); const check = document.createElement('input'); check.type = 'checkbox'; check.dataset.library = library.id; check.value = doc.id; check.checked = selected.has(doc.id);
        label.append(check, el('span', doc.relative_path)); group.append(label);
      }
      const checks = [...group.querySelectorAll('input[data-library]')];
      const syncAll = () => { all.checked = checks.every(input => input.checked); all.indeterminate = !all.checked && checks.some(input => input.checked); };
      all.addEventListener('change', () => checks.forEach(input => input.checked = all.checked));
      checks.forEach(input => input.addEventListener('change', syncAll)); syncAll();
    } else group.append(el('p', '尚无已索引文档。', 'help'));
    $('#libraries').append(group);
  }
  if (!libraries.some(item => item.documents.length)) $('#libraries').append(el('p', '从左侧扫描目录后，文档会出现在这里。', 'help'));
  $('#publication-state').textContent = count ? `已开放 ${count} 份文档；更改勾选后请保存。` : '当前没有开放可查询文档。';
  await updateStatus();
}
async function updateStatus() {
  if (!session || session.must_change) return;
  try {
    const state = await api('status'); $('#web-address').textContent = state.web.url + (state.web.host === '0.0.0.0' ? '（局域网设备请使用服务器 IP）' : '（仅本机）');
    $('#model-status').textContent = state.model.loaded ? '本地模型已加载 · CPU' : state.model.checkpoint_configured ? '本地模型已安装' : '请安装 JEV-models 模型目录';
    const job = state.job; scanning = job?.state === 'running'; $('#job').hidden = !job; $('#scan').disabled = scanning; $('#cancel-job').hidden = !scanning;
    if (job) { $('#job-message').textContent = job.message; $('#job-progress').max = job.total || 1; $('#job-progress').value = job.completed || 0; if (job.state !== 'running' && completedJob !== job.id) { completedJob = job.id; if (job.state === 'completed') { await refresh(); notice('目录扫描完成。选择文档并保存访问范围后，查询端才能使用。'); } else if (job.state === 'failed') notice(job.message, true); } }
  } catch (error) { notice(error.message, true); }
}
async function action(button, work) { button.disabled = true; notice(''); try { await work(); } catch (error) { notice(error.message, true); } finally { button.disabled = button.id === 'scan' && scanning; } }
$('#login-form').addEventListener('submit', event => { event.preventDefault(); action(event.submitter, async () => { await signedIn(await api('login', {username:$('#username').value,password:$('#password').value})); $('#password').value = ''; }); });
$('#password-form').addEventListener('submit', event => { event.preventDefault(); action(event.submitter, async () => { if ($('#new-password').value !== $('#confirm-password').value) throw new Error('两次输入的新密码不一致。'); const value = await api('password', {current_password:$('#current-password').value,new_password:$('#new-password').value}); $('#password-form').reset(); await signedIn(value); notice('管理员密码已更新。'); }); });
$('#scan-form').addEventListener('submit', event => { event.preventDefault(); action(event.submitter, async () => { await api('scan', {path:$('#source').value.trim()}); await updateStatus(); }); });
$('#show-password').addEventListener('click', showPassword);
$('#cancel-password').addEventListener('click', () => signedIn(session));
$('#logout').addEventListener('click', () => action($('#logout'), async () => { await api('logout', {}); showLogin(); notice('已退出管理端。'); }));
$('#refresh').addEventListener('click', () => action($('#refresh'), refresh));
$('#cancel-job').addEventListener('click', () => action($('#cancel-job'), async () => { await api('cancel', {}); await updateStatus(); }));
$('#publish').addEventListener('click', () => action($('#publish'), async () => { const grants = libraries.map(library => ({library_id:library.id,generation:library.generation,document_ids:[...document.querySelectorAll('input[data-library]:checked')].filter(input => input.dataset.library === library.id).map(input => input.value)})).filter(grant => grant.document_ids.length); await api('publication', {grants}); await refresh(); notice('访问范围已保存，查询端已更新。'); }));
$('#unpublish').addEventListener('click', () => action($('#unpublish'), async () => { await api('publication', {grants:[]}); await refresh(); notice('已关闭全部资料访问。'); }));
api('session').then(signedIn).catch(showLogin);
