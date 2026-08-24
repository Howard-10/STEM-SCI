import { useEffect, useMemo, useState } from "react";
import {
  authApi,
  readStoredAuth,
  type ApiDocumentVersion,
  type ApiProjectDocument,
} from "../api/auth";
import type { WorkspaceTab } from "../App";
import { demoDocumentContents, demoDocumentsByProject } from "../demo/projectHub";

type PaperEditorPageProps = {
  projectId: string;
  onNavigate: (tab: WorkspaceTab) => void;
};

const defaultDraft = `# 新的研究文档

从研究问题、证据和设计开始记录。`;

function documentLabel(type: ApiProjectDocument["document_type"]) {
  if (type === "manuscript") return "论文正文";
  if (type === "reference") return "参考资料";
  if (type === "dataset") return "数据集";
  if (type === "protocol") return "研究方案";
  return "研究笔记";
}

function renderMarkdown(content: string) {
  return content.split(/\n{2,}/).map((block, index) => {
    const trimmed = block.trim();
    if (!trimmed) return null;
    if (trimmed.startsWith("# ")) return <h1 key={index}>{trimmed.slice(2)}</h1>;
    if (trimmed.startsWith("## ")) return <h2 key={index}>{trimmed.slice(3)}</h2>;
    if (trimmed.startsWith("### ")) return <h3 key={index}>{trimmed.slice(4)}</h3>;
    if (trimmed.startsWith("- ")) {
      return (
        <ul key={index}>
          {trimmed.split("\n").filter(Boolean).map((item) => <li key={item}>{item.replace(/^- /, "")}</li>)}
        </ul>
      );
    }
    return <p key={index}>{trimmed}</p>;
  });
}

export function PaperEditorPage({ projectId, onNavigate }: PaperEditorPageProps) {
  const demoMode = import.meta.env.VITE_DEMO_MODE !== "false";
  const token = readStoredAuth()?.access_token;
  const [documents, setDocuments] = useState<ApiProjectDocument[]>(demoDocumentsByProject[projectId] ?? []);
  const [activeDocumentId, setActiveDocumentId] = useState<string | null>(
    (demoDocumentsByProject[projectId] ?? [])[0]?.document_id ?? null,
  );
  const [content, setContent] = useState(defaultDraft);
  const [savedContent, setSavedContent] = useState(defaultDraft);
  const [changeNote, setChangeNote] = useState("完善研究设计与主要结果变量");
  const [versions, setVersions] = useState<ApiDocumentVersion[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("未修改");
  const [error, setError] = useState("");

  const activeDocument = useMemo(
    () => documents.find((document) => document.document_id === activeDocumentId) ?? null,
    [documents, activeDocumentId],
  );

  useEffect(() => {
    let mounted = true;
    setDocuments(demoDocumentsByProject[projectId] ?? []);
    setActiveDocumentId((demoDocumentsByProject[projectId] ?? [])[0]?.document_id ?? null);
    setContent(defaultDraft);
    setSavedContent(defaultDraft);
    setVersions([]);
    setStatus("未修改");

    async function loadDocuments() {
      if (!token) return;
      try {
        const remoteDocuments = await authApi.listDocuments(token, projectId);
        if (!mounted) return;
        setDocuments(remoteDocuments);
        setActiveDocumentId(remoteDocuments[0]?.document_id ?? null);
      } catch {
        if (!mounted || !demoMode) setError("论文文档暂时无法读取");
      }
    }

    void loadDocuments();
    return () => {
      mounted = false;
    };
  }, [demoMode, projectId, token]);

  useEffect(() => {
    if (!activeDocument) return;
    const document = activeDocument;
    let mounted = true;
    setStatus("读取中");

    async function loadVersion() {
      if (!token) {
        const nextContent = demoDocumentContents[document.document_id] ?? defaultDraft;
        if (!mounted) return;
        setContent(nextContent);
        setSavedContent(nextContent);
        setVersions([]);
        setStatus("已加载");
        return;
      }

      try {
        const version = await authApi.getDocumentVersion(
          token,
          projectId,
          document.document_id,
          document.current_version,
        );
        if (!mounted) return;
        setContent(version.content);
        setSavedContent(version.content);
        setVersions([version]);
        setStatus("已加载");
      } catch {
        if (!mounted) return;
        const nextContent = demoDocumentContents[document.document_id] ?? defaultDraft;
        setContent(nextContent);
        setSavedContent(nextContent);
        setStatus("演示内容");
      }
    }

    void loadVersion();
    return () => {
      mounted = false;
    };
  }, [activeDocument, projectId, token]);

  const save = async () => {
    if (!activeDocument || !content.trim()) return;
    const document = activeDocument;
    setBusy(true);
    setError("");
    try {
      if (token) {
        const version = await authApi.saveDocumentVersion(
          token,
          projectId,
          document.document_id,
          content,
          changeNote.trim() || "更新论文内容",
        );
        setVersions((current) => [version, ...current]);
        setDocuments((current) => current.map((item) => item.document_id === document.document_id
          ? { ...document, current_version: version.version, size_bytes: version.size_bytes, updated_at: version.created_at }
          : item));
      } else {
        const nextVersion = document.current_version + 1;
        setVersions((current) => [{
          document_id: document.document_id,
          project_id: projectId,
          version: nextVersion,
          format: document.format,
          content,
          sha256: `demo-local-${Date.now()}`,
          size_bytes: content.length,
          storage_ref: `demo://documents/${document.document_id}/v${nextVersion}`,
          change_note: changeNote.trim() || "更新论文内容",
          created_by: "user-demo",
          created_at: new Date().toISOString(),
        }, ...current]);
        setDocuments((current) => current.map((item) => item.document_id === document.document_id
          ? { ...item, current_version: nextVersion, size_bytes: content.length, updated_at: new Date().toISOString() }
          : item));
      }
      setSavedContent(content);
      setStatus("已保存新版本");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "版本保存失败");
    } finally {
      setBusy(false);
    }
  };

  const createDocument = async () => {
    setBusy(true);
    setError("");
    try {
      if (token) {
        const document = await authApi.createDocument(token, projectId, {
          title: "新的研究笔记",
          document_type: "note",
          format: "markdown",
          content: defaultDraft,
          change_note: "创建研究笔记",
        });
        setDocuments((current) => [document, ...current]);
        setActiveDocumentId(document.document_id);
      } else {
        const document: ApiProjectDocument = {
          document_id: `demo-note-${Date.now()}`,
          project_id: projectId,
          title: "新的研究笔记",
          document_type: "note",
          format: "markdown",
          status: "active",
          current_version: 1,
          current_sha256: `demo-${Date.now()}`,
          size_bytes: defaultDraft.length,
          created_by: "user-demo",
          updated_by: "user-demo",
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        setDocuments((current) => [document, ...current]);
        setActiveDocumentId(document.document_id);
        setContent(defaultDraft);
        setSavedContent(defaultDraft);
      }
      setStatus("已创建");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "文档创建失败");
    } finally {
      setBusy(false);
    }
  };

  const dirty = content !== savedContent;

  return (
    <div className="workspace editor-page">
      <header className="page-hero">
        <div>
          <span className="eyebrow">PAPER EDITOR</span>
          <h1>论文编辑区</h1>
          <p>用 Markdown 管理论文正文、研究方案和版本记录，回答中的证据可以回到这里继续写。</p>
        </div>
        <div className="hero-actions">
          <button className="secondary-action" onClick={() => onNavigate("workspace")} type="button">回到工作台</button>
          <button className="primary-action" onClick={() => onNavigate("agent")} type="button">打开 Agent / Codex</button>
        </div>
      </header>

      <div className="editor-layout">
        <aside className="editor-sidebar panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">PROJECT DOCUMENTS</span>
              <h2>项目资料</h2>
            </div>
            <span className="status-badge status-ready">{documents.length} 个</span>
          </div>
          <div className="editor-project-chip">
            <span>当前项目</span>
            <strong>{projectId}</strong>
          </div>
          <div className="document-stack">
            {documents.map((document) => (
              <button
                className={`document-row ${activeDocumentId === document.document_id ? "selected" : ""}`}
                key={document.document_id}
                onClick={() => setActiveDocumentId(document.document_id)}
                type="button"
              >
                <div className="card-topline">
                  <strong>{document.title}</strong>
                  <span className="status-badge status-muted">{documentLabel(document.document_type)}</span>
                </div>
                <span>{document.format} · v{document.current_version}</span>
              </button>
            ))}
          </div>
          <button className="secondary-action full-width" disabled={busy} onClick={() => void createDocument()} type="button">
            + 新建 Markdown 文档
          </button>
          <div className="editor-side-note">
            <strong>版本化保存</strong>
            <span>每次保存都会生成新版本，旧内容仍可追溯和恢复。</span>
          </div>
        </aside>

        <main className="editor-main panel">
          <div className="editor-toolbar">
            <div>
              <span className="eyebrow">MARKDOWN MANUSCRIPT</span>
              <h2>{activeDocument?.title ?? "选择一个文档"}</h2>
            </div>
            <div className="editor-status">
              <span className={dirty ? "editor-dirty" : "editor-clean"}>{dirty ? "有未保存修改" : status}</span>
              <span>v{activeDocument?.current_version ?? 1}</span>
            </div>
          </div>
          <div className="editor-split">
            <section className="editor-canvas">
              <div className="editor-canvas-topline">
                <span>编辑</span>
                <span>Markdown</span>
              </div>
              <textarea
                aria-label="Markdown 论文正文"
                disabled={!activeDocument}
                onChange={(event) => {
                  setContent(event.target.value);
                  setStatus("正在编辑");
                }}
                value={content}
              />
            </section>
            <section className="markdown-preview" aria-label="Markdown 预览">
              <div className="editor-canvas-topline">
                <span>预览</span>
                <span>Live</span>
              </div>
              <article>{renderMarkdown(content)}</article>
            </section>
          </div>
        </main>

        <aside className="editor-right">
          <section className="panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">SAVE VERSION</span>
                <h3>保存版本</h3>
              </div>
            </div>
            <label className="editor-field">
              <span>修改说明</span>
              <input value={changeNote} onChange={(event) => setChangeNote(event.target.value)} />
            </label>
            <button className="primary-action full-width" disabled={busy || !activeDocument || !dirty} onClick={() => void save()} type="button">
              {busy ? "保存中..." : "保存为新版本"}
            </button>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">VERSION HISTORY</span>
                <h3>版本记录</h3>
              </div>
              <span className="result-count">{versions.length} 条</span>
            </div>
            <div className="version-list">
              {versions.length ? versions.map((version) => (
                <button className="version-row" key={`${version.document_id}-${version.version}`} onClick={() => setContent(version.content)} type="button">
                  <strong>v{version.version}</strong>
                  <span>{version.change_note ?? "未填写说明"}</span>
                  <small>{new Date(version.created_at).toLocaleString("zh-CN")}</small>
                </button>
              )) : <div className="empty-state small-empty"><strong>暂无远程版本记录</strong><span>保存后会显示版本历史。</span></div>}
            </div>
          </section>

          <section className="panel editor-reference-card">
            <span className="eyebrow">WORKFLOW LINK</span>
            <h3>把回答带回论文</h3>
            <p>在研究工作台打开回答依据，再将证据和研究设计整理到当前文档。</p>
            <button className="secondary-action full-width" onClick={() => onNavigate("workspace")} type="button">打开回答与证据</button>
          </section>
        </aside>
      </div>

      {error && <p className="error-text" role="alert">{error}</p>}
    </div>
  );
}
