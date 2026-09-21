"use strict";
const el = id => document.getElementById(id);
let config, currentJob, queryController, readerRequest = 0;
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Error(typeof data.detail === "string" ? data.detail : "请求未完成，请检查输入。");
  return data;
}
const post = (path, data) => api(path, { method:"POST", ...(data ? {headers:{"Content-Type":"application/json"},body:JSON.stringify(data)} : {}) });
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function message(text, error = false) { el("message").textContent = text; el("message").className = error ? "error" : ""; }
async function refresh() {
  const [metadata, list] = await Promise.all([api("/api/config"), api("/api/documents")]);
  const next = {...metadata, ...list.status};
  if (config && (next.library_id !== config.library_id || next.generation !== config.generation)) {
    queryController?.abort(); el("results").replaceChildren(); el("reader").replaceChildren();
    readerRequest++; message("索引已更新，请重新检索。");
  }
  config = next; currentJob = next.job;
  el("path").value = next.source_root.path;
  el("status").textContent = next.documents + " 份文档 · " + next.coverage.native_blocks + " 个原文单元 · " + next.coverage.images_recognized + " 处图片已识别";
  if (!next.source_root.available) el("status").textContent += " · 源目录当前不可访问";
  el("documents").replaceChildren();
  for (const doc of list.documents) {
    const button = node("button", doc.name); button.onclick = () => readDocument(doc).catch(error => message(error.message,true));
    el("documents").append(button);
  }
  renderJob();
}
function renderJob() {
  const busy = currentJob?.state === "running";
  el("job").textContent = currentJob ? currentJob.message + (busy ? " ("+currentJob.completed+"/"+(currentJob.total || "…")+")" : "") : "";
  el("cancel-job").hidden = !busy;
  for (const button of el("source-form").querySelectorAll("button")) button.disabled = busy;
  el("scan").disabled = busy; el("files").disabled = busy;
}
async function start(path, body) {
  try { const data = await post(path,body); currentJob=data.job; renderJob(); }
  catch(error) { message(error.message,true); }
}
el("source-form").onsubmit = event => { event.preventDefault(); start("/api/source-root",{path:el("path").value.trim()}); };
el("browse").onclick = async () => {
  el("browse").disabled=true;
  try { const data=await post("/api/source-root/pick"); if(!data.cancelled) el("path").value=data.path; }
  catch(error) { message(error.message,true); }
  finally { el("browse").disabled=false; }
};
el("default").onclick = () => { if(config) el("path").value=config.source_root.default_path; };
el("scan").onclick = () => start("/api/documents/scan-workspace");
el("cancel-job").onclick = async () => { try {currentJob=(await post("/api/index/jobs/"+currentJob.id+"/cancel")).job;renderJob();} catch(error){message(error.message,true);} };
el("files").onchange = async event => {
  const files=[...event.target.files]; event.target.value=""; if(!files.length)return;
  const body=new FormData(); files.forEach(file=>body.append("files",file));
  try {currentJob=(await api("/api/documents/upload",{method:"POST",body})).job;renderJob();}
  catch(error){message(error.message,true);}
};
async function readDocument(target) {
  const request=++readerRequest;
  const params=new URLSearchParams({library_id:target.library_id||config.library_id,generation:target.generation||config.generation});
  const id=target.document_id||target.id;
  const data=await api("/api/documents/"+id+"?"+params);
  if(request!==readerRequest)return;
  const area=el("reader"); area.replaceChildren(node("h3",data.document.name));
  const link=node("a","下载完整文件");link.href="/api/documents/"+id+"/raw?"+params;area.append(link);
  for(const block of data.blocks){
    const section=node("section",undefined,"source-block"+(target.block_id===block.id?" highlighted":""));
    section.id="block-"+block.id;
    section.append(node("small",block.locator.label+(block.kind==="ocr"?" · 图片识别文字":"")));
    section.append(node("p",block.text || (block.ocr_status==="no_text"?"未识别到文字":"图片未能识别，请核对原文件")));
    if(block.asset_id){
      const details=node("details"); details.append(node("summary","核对原图"));
      const img=node("img");img.src="/api/media/"+block.asset_id;img.alt=block.locator.label+"原图";
      img.width=block.width||1;img.height=block.height||1;img.loading="lazy";details.append(img);section.append(details);
    }
    area.append(section);
  }
  if(target.block_id) document.getElementById("block-"+target.block_id)?.scrollIntoView({block:"center"});
}
el("query-form").onsubmit = async event => {
  event.preventDefault(); if(!config)return;
  queryController?.abort(); const controller=new AbortController();queryController=controller;
  readerRequest++;el("reader").replaceChildren();el("ask").disabled=true;message("正在检索，本地模型首次加载可能稍久…");el("results").replaceChildren();
  try {
    const result=await api("/api/query",{method:"POST",headers:{"Content-Type":"application/json"},signal:controller.signal,
      body:JSON.stringify({question:el("question").value.trim(),top_k:12,max_evidence:3,library_id:config.library_id})});
    if(controller.signal.aborted)return;
    if(result.library_id!==config.library_id||result.generation!==config.generation){message("索引已更新，请重新检索。");return;}
    message(result.evidence.length ? "找到 "+result.evidence.length+" 个相关段落。请核对原文。" : result.answer);
    for(const item of result.evidence) {
      const card=node("article");card.append(node("h3",item.document_name),node("small",item.locator.label+(item.kind==="ocr"?" · 图片识别，需核对原图":"")),node("p",item.text));
      const button=node("button","定位原文");button.onclick=()=>readDocument(item).catch(error=>message(error.message,true));card.append(button);el("results").append(card);
    }
  } catch(error){if(error.name!=="AbortError")message(error.message,true);}
  finally {if(queryController===controller)el("ask").disabled=false;}
};
let polling=false;
setInterval(async()=>{
  if(currentJob?.state!=="running"||polling)return;
  polling=true;
  try {
    currentJob=(await api("/api/index/job")).job;renderJob();
    if(currentJob.state!=="running"){
      const state=currentJob.state,detail=currentJob.message;await refresh();message(detail,state==="failed");
    }
  }catch(error){message(error.message,true);}finally{polling=false;}
},1000);
refresh().catch(error=>message("本机服务连接失败："+error.message,true));
