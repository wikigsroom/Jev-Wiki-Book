const form = document.querySelector('#query-form');
const results = document.querySelector('#results');
const message = document.querySelector('#message');
const button = document.querySelector('#search');
fetch('/api/health').then(r => r.json()).then(data => {
  document.querySelector('#availability').textContent = data.available ? '资料服务已就绪' : '等待管理员开放资料';
}).catch(() => { document.querySelector('#availability').textContent = '服务暂时无法连接'; });
function element(tag, text, cls) { const node = document.createElement(tag); node.textContent = text; if (cls) node.className = cls; return node; }
form.addEventListener('submit', async event => {
  event.preventDefault();
  const question = document.querySelector('#question').value.trim();
  if (!question || button.disabled) return;
  button.disabled = true; results.replaceChildren(); message.textContent = '正在查找相关原文，首次查询可能需要较长时间…';
  try {
    const response = await fetch('/api/query', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '查询失败，请检查输入。');
    message.textContent = data.evidence.length ? `找到 ${data.evidence.length} 处相关原文` : data.message;
    for (const item of data.evidence) {
      const card = element('article', '', 'quote-card');
      const heading = element('div', '', 'quote-heading');
      heading.append(element('span', item.citation_id, 'citation'), element('h2', item.document_name), element('span', item.label, 'locator'));
      const copy = element('button', '复制原文', 'quiet'); copy.type = 'button';
      copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(item.text); copy.textContent = '已复制'; } catch { copy.textContent = '请选中原文复制'; } });
      card.append(heading, element('blockquote', item.text), copy); results.append(card);
    }
  } catch (error) { message.textContent = error.message || '无法连接查询服务，请稍后重试。'; }
  finally { button.disabled = false; }
});
