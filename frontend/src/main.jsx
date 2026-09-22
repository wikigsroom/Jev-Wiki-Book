import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const icons = {
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  folder: <path d="M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z" />,
  file: <><path d="M14 3H5v18h14V8l-5-5Z" /><path d="M14 3v5h5M8 12h8M8 16h6" /></>,
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  upload: <><path d="M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5" /></>,
  refresh: <><path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5" /></>,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  check: <path d="m5 12 4 4L19 6" />,
  link: <><path d="m10 14 4-4M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0" transform="translate(1 0) scale(.9)" /></>,
  settings: <><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="8" cy="6" r="2" /><circle cx="16" cy="12" r="2" /><circle cx="10" cy="18" r="2" /></>,
  shield: <><path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z" /><path d="m8 12 3 3 5-6" /></>,
  copy: <><rect x="8" y="8" width="12" height="13" rx="2" /><path d="M16 8V3H3v13h5" /></>,
  download: <><path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4" /></>,
  warning: <><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3v1" /></>,
  image: <><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8" cy="8" r="1.5" /><path d="m3 17 6-6 4 4 3-3 5 5" /></>,
  trash: <><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7" /></>,
  chevron: <path d="m9 5 7 7-7 7" />,
  book: <><path d="M12 5v16M3 3l9 2 9-2v16l-9 2-9-2V3Z" /></>,
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
};
function Icon({ name, size = 18, ...props }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{icons[name] || icons.file}</svg>;
}
const number = new Intl.NumberFormat("zh-CN");
const date = new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
const fileSize = size => size >= 1048576 ? number.format(Math.round(size / 104857.6) / 10) + " MB" : size >= 1024 ? number.format(Math.round(size / 1024)) + " KB" : number.format(size) + " B";
function Spinner() { return <span className="spinner" aria-hidden="true" />; }
async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, options); }
  catch (error) { if (error.name === "AbortError") throw error; throw new Error("无法连接本机服务。请启动 JEV 后重试。"); }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "请求未完成，请检查输入后重试。");
  return body;
}
const post = (path, data) => api(path, { method: "POST", ...(data ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) } : {}) });
function setUrl(values) {
  const url = new URL(location.href);
  Object.entries(values).forEach(([key, value]) => value ? url.searchParams.set(key, value) : url.searchParams.delete(key));
  history.replaceState(null, "", url);
}
function Modal({ title, open, onClose, children, wide = false }) {
  const ref = useRef(null);
  useEffect(() => { if (open && !ref.current.open) ref.current.showModal(); if (!open && ref.current.open) ref.current.close(); }, [open]);
  return <dialog ref={ref} className={"modal " + (wide ? "wide-modal" : "")} onCancel={onClose} onClose={onClose} aria-label={title} onClick={event => { if (event.target === ref.current) onClose(); }}>
    <div className="modal-heading"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭窗口"><Icon name="close" /></button></div>
    {children}
  </dialog>;
}
function Kind({ block }) {
  return <span className={"source-kind " + (block.kind === "ocr" ? "is-ocr" : "")}>{block.kind === "ocr" ? "图片识别" : block.kind === "table_row" ? "表格" : "原文"}</span>;
}
function FileMark({ name }) { return <span className="file-mark"><Icon name="file" size={22} /><small>{name.split(".").pop().toUpperCase().slice(0,4)}</small></span>; }
function QuoteText({ block, selected }) {
  if (!selected || !Number.isInteger(selected.char_start)) return block.text;
  const from = selected.char_start, to = selected.char_end;
  return <>{block.text.slice(0, from)}<mark>{block.text.slice(from, to)}</mark>{block.text.slice(to)}</>;
}

function App() {
  const [config, setConfig] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [view, setView] = useState(new URLSearchParams(location.search).get("view") === "library" ? "library" : "search");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [searching, setSearching] = useState(false);
  const [queryError, setQueryError] = useState("");
  const [filter, setFilter] = useState(new URLSearchParams(location.search).get("filter") || "");
  const [job, setJob] = useState(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [sourcePath, setSourcePath] = useState("");
  const [sourceError, setSourceError] = useState("");
  const [sourcePicking, setSourcePicking] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sharing, setSharing] = useState(null);
  const [sharingBusy, setSharingBusy] = useState(false);
  const [sharingError, setSharingError] = useState("");
  useEffect(() => { if (settingsOpen) api("/api/sharing").then(setSharing).catch(reason => setSharingError(reason.message)); }, [settingsOpen]);
  async function saveSharing(event) {
    event.preventDefault(); setSharingBusy(true); setSharingError("");
    try { setSharing(await post("/api/sharing", { enabled: sharing.enabled, port: Number(sharing.port), lan: sharing.lan })); notify("查询端设置已保存"); }
    catch (reason) { setSharingError(reason.message); api("/api/sharing").then(setSharing).catch(() => {}); }
    finally { setSharingBusy(false); }
  }
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [reader, setReader] = useState(null);
  const [readerTarget, setReaderTarget] = useState(null);
  const [readerBusy, setReaderBusy] = useState(false);
  const [readerError, setReaderError] = useState("");
  const [readerExpanded, setReaderExpanded] = useState(false);
  const [narrow, setNarrow] = useState(window.matchMedia("(max-width: 1180px)").matches);
  const [topK, setTopK] = useState(12);
  const [maxEvidence, setMaxEvidence] = useState(3);
  const queryRef = useRef(null);
  const uploadRef = useRef(null);
  const readerScroll = useRef(null);
  const readerPane = useRef(null);
  const readerPreviousFocus = useRef(null);
  const configRef = useRef(null);
  const queryAbort = useRef(null);
  const readerAbort = useRef(null);
  const completedJob = useRef(null);
  const sourceTrigger = useRef(null);
  const sourceInput = useRef(null);
  const readerRequest = useRef(0);
  const notify = useCallback(text => setToast(text), []);
  useEffect(() => window.jevDesktop?.onSourceSelected(path => { setSourcePath(path); setSourceError(""); setSourceOpen(true); }), []);
  useEffect(() => { window.jevDesktop?.preferences().then(value => { setTopK(value.topK); setMaxEvidence(value.maxEvidence); }).catch(() => {}); }, []);
  const changePreference = (name, value) => {
    if (name === "topK") setTopK(value); else setMaxEvidence(value);
    window.jevDesktop?.preferences({ [name]: value }).catch(() => notify("设置未能保存，下次启动将使用之前的设置。"));
  };
  const closeReader = useCallback((restoreFocus = true) => {
    readerAbort.current?.abort(); readerRequest.current += 1;
    setReader(null); setReaderTarget(null); setReaderBusy(false); setReaderExpanded(false);
    if (restoreFocus) requestAnimationFrame(() => { if (readerPreviousFocus.current?.isConnected) readerPreviousFocus.current.focus(); });
    setUrl({ document: null, block: null, library: null, version: null });
  }, []);
  const refresh = useCallback(async () => {
    const [metadata, list] = await Promise.all([api("/api/config"), api("/api/documents")]);
    // The document response and its status are one pinned snapshot.
    const next = { ...metadata, ...list.status };
    if (configRef.current && (configRef.current.library_id !== next.library_id || configRef.current.generation !== next.generation)) {
      queryAbort.current?.abort(); setSearching(false); setResult(null); setQueryError(""); setFilter(""); setUrl({ filter: null }); closeReader(false);
    }
    configRef.current = next; setConfig(next); setDocuments(list.documents || []); setJob(next.job); setError("");
  }, [closeReader]);
  useEffect(() => { refresh().catch(reason => setError(reason.message)); return () => { queryAbort.current?.abort(); readerAbort.current?.abort(); }; }, [refresh]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(""), 4200); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1180px)");
    const changed = () => setNarrow(media.matches);
    media.addEventListener("change", changed); return () => media.removeEventListener("change", changed);
  }, []);
  useEffect(() => { if (narrow && readerExpanded) readerPane.current?.focus(); }, [narrow, readerExpanded]);
  useEffect(() => {
    function key(event) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); closeReader(false); setView("search"); setUrl({ view: null }); requestAnimationFrame(() => queryRef.current?.focus());
      }
    }
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, [closeReader]);
  useEffect(() => {
    if (job?.state !== "running") return;
    let stopped = false;
    const timer = setInterval(async () => {
      try {
        const next = await api("/api/index/job");
        if (stopped) return;
        setJob(next.job);
        if (next.job && next.job.state !== "running" && completedJob.current !== next.job.id) {
          completedJob.current = next.job.id;
          await refresh();
          if (next.job.state === "failed") setError(next.job.message);
          else notify(next.job.message);
        }
      } catch (reason) { if (!stopped) setError(reason.message); }
    }, 900);
    return () => { stopped = true; clearInterval(timer); };
  }, [job?.state, refresh, notify]);
  useEffect(() => {
    if (!reader || !readerTarget?.block_id) return;
    const target = document.getElementById("source-" + readerTarget.block_id);
    if (target) requestAnimationFrame(() => target.scrollIntoView({ behavior: "instant", block: "center" }));
  }, [reader, readerTarget]);
  const openDocument = useCallback(async (target, reveal = true) => {
    const library = target.library_id || configRef.current?.library_id;
    const generation = target.generation || configRef.current?.generation;
    const documentId = target.document_id || target.id;
    readerAbort.current?.abort();
    const controller = new AbortController(); readerAbort.current = controller;
    const request = ++readerRequest.current;
    if (reveal && !readerPane.current?.contains(document.activeElement)) readerPreviousFocus.current = document.activeElement;
    setReader(null); setReaderBusy(true); setReaderError(""); setReaderTarget(target); setReaderExpanded(reveal);
    setUrl({ document: documentId, block: target.block_id, library, version: generation });
    try {
      const params = new URLSearchParams({ library_id: library, generation });
      const content = await api("/api/documents/" + encodeURIComponent(documentId) + "?" + params, { signal: controller.signal });
      if (request === readerRequest.current) { setReader(content); setReaderBusy(false); if (!target.block_id) readerScroll.current?.scrollTo({ top: 0 }); }
    } catch (reason) { if (reason.name !== "AbortError" && request === readerRequest.current) { setReaderError(reason.message); setReaderBusy(false); } }
  }, []);
  const deepLinked = useRef(false);
  useEffect(() => {
    if (!config || deepLinked.current) return;
    deepLinked.current = true;
    const params = new URLSearchParams(location.search);
    if (params.get("document")) openDocument({ document_id: params.get("document"), block_id: params.get("block"),
      library_id: params.get("library") || config.library_id, generation: params.get("version") || config.generation });
  }, [config, openDocument]);

  const running = job?.state === "running";
  const currentName = config?.source_root?.path.split(/[\\/]/).filter(Boolean).pop() || "文档目录";
  const changeView = value => { setView(value); setUrl({ view: value === "search" ? null : value }); };
  const navigateView = (event, value) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault(); changeView(value);
  };
  const openSource = () => { setSourcePath(config?.source_root?.path || ""); setSourceError(""); setSourceOpen(true); };
  const beginJob = async (path, body) => {
    setActionBusy(true); setError("");
    try { const response = await post(path, body); setJob(response.job); return true; }
    catch (reason) { setError(reason.message); return false; }
    finally { setActionBusy(false); }
  };
  const changeSource = async event => {
    event.preventDefault();
    if (!sourcePath.trim()) { setSourceError("请输入本机目录的完整路径。"); sourceInput.current?.focus(); return; }
    setActionBusy(true); setSourceError("");
    try { const response = await post("/api/source-root", { path: sourcePath.trim() }); setJob(response.job); setSourceOpen(false); }
    catch (reason) { setSourceError(reason.message); sourceInput.current?.focus(); }
    finally { setActionBusy(false); }
  };
  const pickSource = async () => {
    setSourcePicking(true); setSourceError("");
    try { const selection = window.jevDesktop ? await window.jevDesktop.chooseDirectory(sourcePath) : await post("/api/source-root/pick"); if (!selection.cancelled) setSourcePath(selection.path); }
    catch (reason) { setSourceError(reason.message); }
    finally { setSourcePicking(false); }
  };
  const upload = async event => {
    const files = [...event.target.files]; event.target.value = "";
    if (!files.length) return;
    const body = new FormData(); files.forEach(file => body.append("files", file));
    setActionBusy(true);
    try { const response = await api("/api/documents/upload", { method: "POST", body }); setJob(response.job); }
    catch (reason) { setError(reason.message); }
    finally { setActionBusy(false); }
  };
  const ask = async (event, preset) => {
    event?.preventDefault();
    const value = (preset || question).trim();
    if (!value) { setQueryError("输入一个问题或关键词，再开始检索。"); queryRef.current?.focus(); return; }
    if (searching) return;
    if (preset) setQuestion(preset);
    const context = configRef.current;
    if (!context) { setQueryError("服务尚未连接，请重试连接。"); return; }
    queryAbort.current?.abort();
    const controller = new AbortController(); queryAbort.current = controller;
    closeReader(false); setSearching(true); setQueryError(""); setResult(null); changeView("search");
    try {
      const next = await api("/api/query", { method: "POST", signal: controller.signal, headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: value, top_k: topK, max_evidence: maxEvidence, library_id: context.library_id }) });
      if (controller.signal.aborted) return;
      if (configRef.current?.library_id !== next.library_id || configRef.current?.generation !== next.generation) {
        setQueryError("索引已更新，请重新检索。"); return;
      }
      setResult(next);
      if (next.evidence.length) openDocument(next.evidence[0], window.matchMedia("(min-width: 1181px)").matches);
      const nextConfig = await api("/api/config");
      if (controller.signal.aborted) return;
      if (nextConfig.library_id === context.library_id && nextConfig.generation === context.generation) {
        configRef.current = nextConfig; setConfig(nextConfig);
      } else await refresh();
    } catch (reason) { if (reason.name !== "AbortError") setQueryError(reason.message); }
    finally { if (queryAbort.current === controller) setSearching(false); }
  };
  const copy = async text => { try { if (window.jevDesktop) await window.jevDesktop.copyText(text); else await navigator.clipboard.writeText(text); notify("已复制原文与来源"); } catch { notify("复制未完成，请手动选择原文复制。"); } };
  const remove = async () => {
    setActionBusy(true);
    try {
      await api("/api/documents/" + deleteTarget.id + "?generation=" + config.generation, { method: "DELETE" });
      setDeleteTarget(null); await refresh(); notify("已从索引移除，原文件保留");
    } catch (reason) { setError(reason.message); }
    finally { setActionBusy(false); }
  };
  const filteredDocs = documents.filter(doc => doc.name.toLowerCase().includes(filter.toLowerCase()));
  const examples = documents.some(doc => doc.name.includes("BTG"))
    ? ["挖矿收益多久显示一次？", "预计每日收益保留几位小数？", "股票行情数据更新延迟是多少？"]
    : [];
  const coverage = config?.coverage || {};
  const rawLink = reader ? "/api/documents/" + reader.document.id + "/raw?" + new URLSearchParams({ library_id: reader.library_id, generation: reader.generation }) : "#";

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">跳到检索内容</a>
    <aside className="sidebar" inert={narrow && readerExpanded ? true : undefined}>
      <a className="brand" href="/" aria-label="JEV 首页"><span className="brand-symbol"><i /><i /><i /></span><span translate="no">JEV<span className="brand-dot">.</span></span><span className="brand-caption">本地文档检索</span></a>
      <nav className="main-nav" aria-label="主导航">
        <a href="/" className={view === "search" ? "nav-item active" : "nav-item"} onClick={event => navigateView(event, "search")} aria-current={view === "search" ? "page" : undefined}><Icon name="search" /><span>找答案</span><kbd>Ctrl K</kbd></a>
        <a href="/?view=library" className={view === "library" ? "nav-item active" : "nav-item"} onClick={event => navigateView(event, "library")} aria-current={view === "library" ? "page" : undefined}><Icon name="book" /><span>文档库</span><span className="nav-count">{config?.documents ?? "—"}</span></a>
      </nav>
      <div className="library-caption">当前文档目录</div>
      <button ref={sourceTrigger} className="directory-button" onClick={openSource} disabled={running}><span className="folder-square"><Icon name="folder" /></span><span className="directory-title"><strong>{currentName}</strong><small>{config?.documents ?? 0} 份文档</small></span><Icon name="chevron" size={15} /></button>
      <p className="sidebar-path" title={config?.source_root?.path}>{config?.source_root?.path || "连接本机服务…"}</p>
      <div className="sidebar-actions">
        <button className="button secondary" disabled={running || actionBusy} onClick={() => uploadRef.current?.click()}><Icon name="upload" size={16} />导入文档</button>
        <button className="icon-button bordered" title="重新扫描当前目录" aria-label="重新扫描当前目录" disabled={running || actionBusy || !config} onClick={() => beginJob("/api/documents/scan-workspace")}><Icon name="refresh" size={17} /></button>
      </div>
      <input ref={uploadRef} type="file" name="files" className="visually-hidden" tabIndex={-1} aria-label="导入本机文档" multiple accept=".md,.markdown,.txt,.rst,.log,.json,.jsonl,.csv,.html,.htm,.pdf,.docx" onChange={upload} />
      <div className="recent-docs">
        <div className="library-caption">目录中的文档</div>
        {documents.slice(0, 6).map(doc => <button key={doc.id} className={"sidebar-document " + (reader?.document.id === doc.id ? "selected" : "")} onClick={() => openDocument(doc)} title={doc.name}><Icon name="file" size={15} /><span>{doc.name}</span></button>)}
        {documents.length > 6 && <a href="/?view=library" className="text-button show-all" onClick={event => navigateView(event, "library")}>查看全部 {documents.length} 份<Icon name="arrow" size={14} /></a>}
        {!documents.length && <p className="sidebar-empty">选择目录并扫描，或导入第一份文档。</p>}
      </div>
      <div className="sidebar-bottom">
        <div className="local-status"><span className={config ? "status-dot" : "status-dot disconnected"} /><span>{config ? "文档留在本机" : "服务未连接"}</span><Icon name="shield" size={15} /></div>
        <button className="settings-button" onClick={() => setSettingsOpen(true)}><Icon name="settings" size={16} />检索设置与运行状态</button>
      </div>
    </aside>

    <div className="main-shell">
      <header className="topbar" inert={narrow && readerExpanded ? true : undefined}><div className="breadcrumb"><span>我的文档</span><span>/</span><strong>{view === "search" ? "找答案" : "文档库"}</strong></div><div className="topbar-actions"><span className="privacy-note"><Icon name="shield" size={14} />本机处理</span><button className="icon-button mobile-settings" aria-label="检索设置" onClick={() => setSettingsOpen(true)}><Icon name="settings" size={17} /></button><button className="button subtle small" onClick={openSource} disabled={running}><Icon name="folder" size={15} />切换目录</button></div></header>
      {error && <div className="alert error" role="alert"><Icon name="warning" /><span>{error}</span><button className="text-button" onClick={() => refresh().catch(reason => setError(reason.message))}>重试连接</button><button className="icon-button" aria-label="关闭提示" onClick={() => setError("")}><Icon name="close" size={16} /></button></div>}
      {running && <div className="index-progress" role="status" aria-live="polite"><Spinner /><div><strong>正在建立索引 <span>{job.completed} / {job.total || "…"}</span></strong><p>{job.message}</p><progress value={job.completed} max={job.total || 1} /></div><button className="text-button" onClick={() => post("/api/index/jobs/" + job.id + "/cancel").then(data => setJob(data.job)).catch(reason => setError(reason.message))}>取消</button></div>}
      <main id="main-content" className={"workspace " + (readerExpanded ? "reader-open" : "")}>
        <section className="work-pane" inert={narrow && readerExpanded ? true : undefined}>
          {view === "search" ? <>
            <div className="search-heading"><span className="section-eyebrow">带着问题，回到原文</span><h1>在文档里，找到依据。</h1><p>检索相关段落，直接核对来源。每一条结果都来自你的文档。</p></div>
            <form className={"query-form " + (queryError ? "has-error" : "")} onSubmit={ask}>
              <label htmlFor="question" className="visually-hidden">想在文档中查找什么</label>
              <div className="query-input-row"><Icon name="search" size={23} /><textarea id="question" name="question" ref={queryRef} value={question} onChange={event => setQuestion(event.target.value)} autoComplete="off" spellCheck={false} placeholder="输入一个具体问题，或文档中的关键词…" rows={2} maxLength={3000} aria-describedby={queryError ? "query-error" : "query-help"}
                onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); ask(event); } }} /></div>
              <div className="query-bottom"><span id="query-help"><Icon name="folder" size={14} /><span>{currentName}</span><span className="dot-separator">·</span>{config?.documents ?? 0} 份文档</span><button className="button primary" type="submit" disabled={searching || !config}>{searching ? <Spinner /> : <Icon name="arrow" size={17} />}{searching ? "正在检索…" : "查找原文"}</button></div>
            </form>
            {queryError && <p className="field-error" id="query-error" role="alert">{queryError}</p>}
            {config?.needs_reindex && <div className="inline-notice"><Icon name="refresh" /><span>此目录需要建立段落索引。</span><button className="text-button" disabled={running} onClick={() => beginJob("/api/documents/scan-workspace")}>开始扫描</button></div>}
            {config && !config.source_root.available && <div className="inline-notice" role="status"><Icon name="warning" /><span>源目录当前不可访问。正在使用上次索引的文档副本。</span></div>}
            {Boolean(coverage.images_unread) && <div className="inline-notice"><Icon name="image" /><span>{coverage.images_unread} 处图片未能识别，部分内容暂时无法检索。请在文档库中核对。</span></div>}
            {searching ? <div className="search-pending" role="status"><div className="pending-line" /><h2>正在查找相关段落…</h2><p>{config?.local_jev?.loaded ? "本地模型正在核对候选原文。" : "首次检索需要加载本地模型，可能稍久。"}结果会保留来源位置。</p><div className="skeleton" /><div className="skeleton short" /></div>
            : result ? <div className="results">
              <div className="results-heading"><h2>{result.status === "found" ? "找到的相关段落" : result.status === "empty" ? "文档库尚未就绪" : "没有找到足够的依据"}<span>{result.evidence.length}</span></h2><small>{number.format(result.diagnostics.latency_ms / 1000)} 秒</small></div>
              {result.status !== "found" && <div className="no-results"><span className="empty-search-icon"><Icon name="search" size={30} /></span><p>{result.answer}</p><a href="/?view=library" className="button secondary" onClick={event => navigateView(event, "library")}>检查文档库</a></div>}
              {result.evidence.map((item, index) => <article className={"evidence-card " + (readerTarget?.chunk_id === item.chunk_id ? "selected" : "")} key={item.chunk_id}>
                <div className="evidence-top"><span className="citation-marker">{String(index + 1).padStart(2, "0")}</span><div className="evidence-source"><strong>{item.document_name}</strong><span>{item.locator.label}{item.section !== item.document_name && " · " + item.section}</span></div><Kind block={item} /></div>
                <blockquote>{item.text}</blockquote>
                {item.kind === "ocr" && <p className="ocr-note"><Icon name="image" size={13} />图片识别文字，建议对照原图核验。</p>}
                <div className="evidence-actions"><button className="text-button" onClick={() => openDocument(item)}><Icon name="link" size={15} />定位原文<Icon name="arrow" size={15} /></button><button className="icon-button" title="复制原文与来源" aria-label={"复制第 " + (index + 1) + " 条原文与来源"} onClick={() => copy(item.text + "\n\n来源：" + item.document_name + " · " + item.locator.label)}><Icon name="copy" size={16} /></button></div>
              </article>)}
              {result.evidence.length > 0 && <p className="results-note"><Icon name="check" size={14} />展示文档中的原文与识别文字，未生成或改写回答。</p>}
              <details className="diagnostics"><summary>查看本次检索详情</summary><dl><dt>召回段落</dt><dd>{result.diagnostics.retrieval_candidates}</dd><dt>模型检查</dt><dd>{result.diagnostics.local_jev_evaluated}</dd><dt>返回段落</dt><dd>{result.evidence.length}</dd><dt>模型</dt><dd>NanoJev / {result.diagnostics.model.device}</dd></dl><p>模型选择分数用于排序，不代表答案正确率。未检索到的内容不能由模型补写。</p></details>
            </div> : <div className="start-state">
              {examples.length > 0 && <><div className="suggestion-label">可以从这些问题开始</div><div className="suggestions">{examples.map(text => <button key={text} onClick={event => ask(event, text)} disabled={!documents.length || running}>{text}<Icon name="arrow" size={15} /></button>)}</div></>}
              <div className="corpus-overview"><div className="corpus-icon"><Icon name="book" size={28} /></div><div><h2>{documents.length ? "文档已就绪，开始查找。" : "把文档放进来，开始查找。"}</h2><p>{documents.length ? number.format(coverage.native_blocks || 0) + " 个原文单元 · " + number.format(coverage.images_recognized || 0) + " 张图片已识别" : "选择本机目录，或导入 PDF、Word、Markdown 等文件。"}</p></div></div>
              <div className="reading-principles"><span><Icon name="check" size={15} />按段落返回</span><span><Icon name="link" size={15} />定位到来源</span><span><Icon name="shield" size={15} />完全本地运行</span></div>
            </div>}
          </> : <>
            <div className="library-heading"><span className="section-eyebrow">来源决定答案</span><h1>你的文档库<span>{documents.length}</span></h1><p>这里的文档参与当前检索。切换目录后，索引与导入文件分别保存。</p></div>
            <div className="library-toolbar"><label className="filter-field"><Icon name="search" size={17} /><input type="search" name="document-filter" autoComplete="off" aria-label="按文件名筛选" placeholder="按文件名筛选…" value={filter} onChange={event => { setFilter(event.target.value); setUrl({ filter: event.target.value }); }} /></label><button className="button secondary small" disabled={running || actionBusy} onClick={() => uploadRef.current?.click()}><Icon name="upload" size={15} />导入</button></div>
            <div className="coverage-summary"><span><b>{number.format(coverage.native_blocks || 0)}</b> 原文单元</span><span><b>{coverage.images_recognized || 0}</b> 张图片已识别</span>{Boolean(coverage.images_no_text) && <span>{coverage.images_no_text} 张未识别到文字</span>}{Boolean(coverage.images_unread) && <span className="warning-text">{coverage.images_unread} 张未能读取</span>}</div>
            <div className="documents-list">
              {filteredDocs.map(doc => <article className="document-row" key={doc.id}><button className="document-open" onClick={() => openDocument(doc)}><FileMark name={doc.name} /><span><strong>{doc.name}</strong><small>{doc.coverage.native_blocks} 个原文单元 · {doc.coverage.images_recognized} 张图片已识别 · {fileSize(doc.size)}</small><em>{doc.origin === "upload" ? "本目录导入" : doc.relative_path}</em></span></button><button className="icon-button delete-document" aria-label={"从索引移除 " + doc.name} disabled={running} onClick={() => setDeleteTarget(doc)}><Icon name="trash" size={16} /></button></article>)}
              {!filteredDocs.length && <div className="no-results"><Icon name="folder" size={30} /><p>{filter ? "没有匹配这个文件名的文档。" : "这个目录还没有文档。可以扫描目录或导入文件。"}</p></div>}
            </div>
            <p className="library-footnote">{config?.indexed_at ? "上次索引更新于 " + date.format(new Date(config.indexed_at)) : "尚未建立索引"}<button className="text-button" disabled={running || actionBusy} onClick={() => beginJob("/api/index/rebuild")}>重新扫描</button></p>
          </>}
        </section>

        <aside ref={readerPane} tabIndex={-1} role={narrow && readerExpanded ? "dialog" : undefined} aria-modal={narrow && readerExpanded ? true : undefined} className={"reader-pane " + (readerExpanded ? "expanded" : "")} aria-label="原文阅读器" onKeyDown={event => {
          if (!narrow || !readerExpanded) return;
          if (event.key === "Escape") { event.preventDefault(); closeReader(); }
          if (event.key === "Tab") {
            const items = [...readerPane.current.querySelectorAll('button:not(:disabled), a[href], summary')].filter(item => item.getClientRects().length);
            const first = items[0], last = items[items.length - 1];
            if (event.shiftKey && (document.activeElement === first || document.activeElement === readerPane.current)) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
          }
        }}>
          <div className="reader-bar"><span><Icon name="book" size={17} />原文阅读器</span><div>{reader && <a className="icon-button" href={rawLink} title="下载完整文件" aria-label="下载完整文件"><Icon name="download" size={17} /></a>}<button className="icon-button reader-close" onClick={closeReader} aria-label="关闭原文阅读器"><Icon name="close" size={17} /></button></div></div>
          {readerBusy ? <div className="reader-loading" role="status"><Spinner />正在读取原文…</div> : readerError ? <div className="reader-loading" role="alert"><p>{readerError}</p></div> : reader ? <>
            <div className="reader-title"><span className="reader-file-type">{reader.document.name.split(".").pop().toUpperCase()}</span><h2>{reader.document.name}</h2><p>{reader.document.coverage.native_blocks} 个原文单元{readerTarget?.locator && <span> · 当前定位：{readerTarget.locator.label}</span>}</p></div>
            <div className="reader-content" ref={readerScroll}>
              {reader.blocks.map(block => <section id={"source-" + block.id} tabIndex={-1} key={block.id} className={"source-block " + (readerTarget?.block_id === block.id ? "highlighted" : "")}>
                <div className="source-block-label"><span>{block.locator.label}</span>{block.kind === "ocr" && <Kind block={block} />}{readerTarget?.block_id === block.id && <span className="hit-label">命中位置</span>}</div>
                {block.text && <p><QuoteText block={block} selected={readerTarget?.block_id === block.id ? readerTarget : null} /></p>}
                {block.kind === "image" && <p className="image-placeholder">{block.ocr_status === "no_text" ? "这张图片未识别到文字。" : "这张图片未能识别，需查看原图。"}</p>}
                {block.asset_id && <details className="source-image"><summary><Icon name="image" size={14} />核对原图</summary><img src={"/api/media/" + block.asset_id} alt={reader.document.name + "，" + block.locator.label + "的原始图片"} width={block.width || 1} height={block.height || 1} loading="lazy" /><span>识别文字可能存在误差，请以原图为准。</span></details>}
              </section>)}
              {reader.document.coverage.warnings?.map(warning => <p key={warning} className="inline-warning">{warning}</p>)}
              <div className="document-end">已到文档末尾<a href={rawLink}>下载完整文件<Icon name="download" size={14} /></a></div>
            </div>
          </> : <div className="reader-empty"><div className="paper-preview" aria-hidden="true"><span className="paper-fold" /><div className="paper-lines"><i /><i /><i className="marked" /><i className="marked" /><i /><i /></div><span className="paper-bookmark"><Icon name="link" size={17} /></span></div><h2>答案有出处。</h2><p>点击一条检索结果，<br />在这里查看命中段落及上下文。</p><span className="reader-empty-label">原文 · 表格 · 图片</span></div>}
        </aside>
      </main>
      <footer className="footer"><span><span translate="no">JEV</span> · 每一条结果，都能回到原文</span><span>{config?.indexed_at ? "索引已更新 " + date.format(new Date(config.indexed_at)) : "等待建立索引"}</span></footer>
    </div>

    <Modal title="选择文档目录" open={sourceOpen} onClose={() => setSourceOpen(false)}>
      <p className="modal-copy">选择你要检索的本机文件夹。新目录扫描完成后自动切换，原目录的索引会保留。</p>
      <form onSubmit={changeSource}>
        <label className="form-label" htmlFor="source-path">文件夹路径</label>
        <div className="path-input"><input ref={sourceInput} id="source-path" name="source-path" value={sourcePath} onChange={event => setSourcePath(event.target.value)} placeholder="例如 C:\文档…" autoComplete="off" spellCheck={false} aria-invalid={Boolean(sourceError)} aria-describedby={sourceError ? "source-error" : undefined} /><button className="button secondary" type="button" onClick={pickSource} disabled={sourcePicking}>{sourcePicking ? <Spinner /> : <Icon name="folder" />}{sourcePicking ? "选择窗口已打开…" : "浏览本机"}</button></div>
        {sourceError && <p className="field-error" id="source-error" role="alert">{sourceError}</p>}
        <button type="button" className="text-button default-source" onClick={() => setSourcePath(config?.source_root?.default_path || "")}>使用默认 JEV 目录</button>
        {config?.libraries?.length > 0 && <div className="recent-libraries"><div className="form-label">已使用的目录</div>{config.libraries.map(library => <button key={library.id} type="button" onClick={() => setSourcePath(library.path)}><Icon name="folder" size={16} /><span>{library.path}</span>{library.active && <small>当前</small>}</button>)}</div>}
        <div className="modal-actions"><button className="button secondary" type="button" onClick={() => setSourceOpen(false)}>取消</button><button className="button primary" type="submit" disabled={running || actionBusy || sourcePicking}>{actionBusy && <Spinner />}扫描并使用此目录</button></div>
      </form>
    </Modal>
    <Modal title="检索设置与运行状态" open={settingsOpen} onClose={() => setSettingsOpen(false)}>
      <div className="settings-fields"><label htmlFor="top-k">候选段落数量<select id="top-k" name="top-k" value={topK} onChange={event => changePreference("topK", Number(event.target.value))}>{[4,8,12,20,30].map(value => <option key={value} value={value}>{value} 个</option>)}</select></label><label htmlFor="max-evidence">最多返回段落<select id="max-evidence" name="max-evidence" value={maxEvidence} onChange={event => changePreference("maxEvidence", Number(event.target.value))}>{[1,2,3,4,6].map(value => <option key={value} value={value}>{value} 个</option>)}</select></label></div>
      <p className="modal-copy">候选数量越多，检查范围越大，也需要更长时间。只返回通过筛选的内容。</p>
      {sharing && <form className="sharing-settings" onSubmit={saveSharing}>
        <h3>浏览器查询端</h3><p className="modal-copy">允许浏览器查询当前已建立的文档库。目录管理、导入和删除仍由桌面端完成。</p>
        <label className="sharing-toggle"><input type="checkbox" checked={sharing.enabled} onChange={event => setSharing({ ...sharing, enabled: event.target.checked })} />启用 Web 查询端</label>
        <div className="settings-fields"><label htmlFor="web-port">访问端口<input id="web-port" type="number" min="1024" max="65535" value={sharing.port} onChange={event => setSharing({ ...sharing, port: event.target.value })} required /></label><label htmlFor="web-scope">访问范围<select id="web-scope" value={sharing.lan ? "lan" : "local"} onChange={event => setSharing({ ...sharing, lan: event.target.value === "lan" })}><option value="local">仅本机</option><option value="lan">局域网</option></select></label></div>
        {sharing.running && <p className="sharing-address">本机访问地址 <span>{sharing.url}</span>{sharing.lan && <small>其他设备使用本机的局域网 IP 和上述端口访问。可连接此端口的人均可查询当前资料。</small>}</p>}
        {(sharingError || sharing.error) && <p className="field-error" role="alert">{sharingError || sharing.error}</p>}
        <button type="submit" className="button secondary" disabled={sharingBusy}>{sharingBusy ? "正在应用…" : "应用查询端设置"}</button>
      </form>}
      <dl className="system-details"><dt>本地决策模型</dt><dd>NanoJev · Qwen3-0.6B</dd><dt>模型状态</dt><dd>{config?.local_jev?.loaded ? "已加载 · " + config.local_jev.device : config?.local_jev?.checkpoint_configured ? "已安装，首次检索时加载" : "未安装"}</dd><dt>图片文字识别</dt><dd>{config?.ocr?.configured ? "RapidOCR · 本地权重已安装" : "本地 OCR 权重未安装"}</dd><dt>回答方式</dt><dd>原文摘录，不生成回答</dd></dl>
      <p className="model-limitation">当前使用社区 NanoJev 游戏决策权重，仅通过当前文档的小样本回归，尚无通用检索质量验证。排序分数不能作为事实正确率；重要信息请核对原文与原图。</p>
      <div className="modal-actions"><button className="button primary" onClick={() => setSettingsOpen(false)}>完成</button></div>
    </Modal>
    <Modal title="从索引移除文档" open={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)}>
      <p className="modal-copy">移除“{deleteTarget?.name}”后，它将不再参与当前检索。本机原文件与历史引用保留；重新扫描可再次导入目录中的文件。</p>
      <div className="modal-actions"><button className="button secondary" onClick={() => setDeleteTarget(null)}>取消</button><button className="button danger" disabled={actionBusy} onClick={remove}>移除文档</button></div>
    </Modal>
    <div className={"toast " + (toast ? "visible" : "")} role="status" aria-live="polite"><Icon name="check" size={17} />{toast}</div>
  </div>;
}
createRoot(document.getElementById("root")).render(<App />);
