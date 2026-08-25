import { generateLatex, listLatexTemplates, type LatexResponse, type LatexTemplate } from "../api/latex";
import { useEffect, useState } from "react";

const fallbackTemplates: LatexTemplate[] = [
  { template_id: "generic-article", name: "通用 STEM 论文（Article）", venue_type: "generic", publisher: "STEM-SCI", description: "通用预投稿模板。", version: "1.0.0", source_url: null, official_status: "generic", document_class: "article", supports_bibliography: true },
  { template_id: "ieee-conference", name: "IEEE Conference（社区映射）", venue_type: "conference", publisher: "IEEE", description: "IEEEtran 会议结构，请以目标会议官网为准。", version: "1.0.0", source_url: "https://www.ieee.org/conferences/publishing/templates.html", official_status: "community", document_class: "IEEEtran", supports_bibliography: true },
  { template_id: "springer-nature", name: "Springer Nature（社区映射）", venue_type: "journal", publisher: "Springer Nature", description: "Springer Nature 期刊结构，请以目标期刊官网为准。", version: "1.0.0", source_url: "https://www.springernature.com/gp/authors/campaigns/latex", official_status: "community", document_class: "sn-jnl", supports_bibliography: true },
];

export function LatexFormatterPage({ projectId }: { projectId: string }) {
  const [templates, setTemplates] = useState<LatexTemplate[]>(fallbackTemplates);
  const [templateId, setTemplateId] = useState("generic-article");
  const [title, setTitle] = useState("A STEM Research Manuscript");
  const [authors, setAuthors] = useState("Author One\nAuthor Two");
  const [abstract, setAbstract] = useState("");
  const [content, setContent] = useState("# Introduction\n\nWrite the manuscript body here.\n\n## Methods\n\nDescribe the method and results.");
  const [keywords, setKeywords] = useState("STEM, research");
  const [result, setResult] = useState<LatexResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [templateBusy, setTemplateBusy] = useState(false);
  const [error, setError] = useState("");

  const loadTemplates = async () => {
    setTemplateBusy(true);
    try {
      const remote = await listLatexTemplates();
      setTemplates(remote);
      if (!remote.some((template) => template.template_id === templateId)) setTemplateId(remote[0]?.template_id ?? "generic-article");
      setError("");
    } catch {
      setError("当前使用内置模板；后端模板接口暂不可用");
    } finally { setTemplateBusy(false); }
  };

  useEffect(() => {
    void loadTemplates();
    const timer = window.setInterval(() => { void loadTemplates(); }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  const generate = async () => {
    setBusy(true); setError("");
    try {
      setResult(await generateLatex({ template_id: templateId, title, authors: authors.split("\n").map((item) => item.trim()).filter(Boolean), abstract, content, keywords: keywords.split(",").map((item) => item.trim()).filter(Boolean), bibliography: "", compile_pdf: true }));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "LaTeX 生成失败"); }
    finally { setBusy(false); }
  };

  const download = () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([result.latex], { type: "application/x-tex" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${projectId || "manuscript"}.tex`; anchor.click(); URL.revokeObjectURL(url);
  };

  return <div className="workspace editor-page latex-page">
    <header className="page-hero"><div><span className="eyebrow">LATEX SUBMISSION FORMATTER</span><h1>投稿格式化</h1><p>选择目标期刊或会议模板，将论文草稿转换为可审计的标准 LaTeX。</p></div></header>
    <div className="formatter-layout latex-layout"><section className="panel formatter-form latex-form-panel">
      <div className="panel-heading"><div><span className="eyebrow">VENUE TEMPLATE</span><h2>选择投稿模板</h2></div><span className="status-badge">{templates.length} 个可用</span></div>
      <label className="editor-field"><span>投稿模板</span><select value={templateId} onChange={(event) => setTemplateId(event.target.value)}>{templates.map((template) => <option key={template.template_id} value={template.template_id}>{template.name} · {template.official_status}</option>)}</select></label>
      <p className="template-note">{templates.find((template) => template.template_id === templateId)?.description}</p>
      {error && <div className="template-health"><span>{error}</span><button type="button" onClick={() => void loadTemplates()} disabled={templateBusy}>{templateBusy ? "检查中..." : "重试模板接口"}</button></div>}
      <label className="editor-field"><span>论文标题</span><input value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <label className="editor-field"><span>作者（每行一位）</span><textarea rows={3} value={authors} onChange={(event) => setAuthors(event.target.value)} /></label>
      <label className="editor-field"><span>摘要</span><textarea rows={4} value={abstract} onChange={(event) => setAbstract(event.target.value)} /></label>
      <label className="editor-field"><span>关键词（逗号分隔）</span><input value={keywords} onChange={(event) => setKeywords(event.target.value)} /></label>
      <label className="editor-field"><span>正文 Markdown</span><textarea className="formatter-body" value={content} onChange={(event) => setContent(event.target.value)} /></label>
      <button className="primary-action full-width latex-generate-button" disabled={busy} onClick={() => void generate()} type="button">{busy ? "生成与编译中..." : "生成标准 LaTeX"}</button>
    </section><section className="panel formatter-output latex-output-panel"><div className="panel-heading"><div><span className="eyebrow">VALIDATED OUTPUT</span><h2>LaTeX 输出</h2></div>{result && <button className="secondary-action" onClick={download} type="button">下载 .tex</button>}</div>
      {result ? <><div className="formatter-status"><strong>{result.compile.status === "compiled" ? "PDF 编译成功" : result.compile.status === "skipped" ? "源码校验完成" : "编译失败"}</strong><span>SHA256 {result.sha256.slice(0, 16)}...</span></div>{result.validation_errors.map((item) => <p className="error-text" key={item}>{item}</p>)}{result.validation_warnings.map((item) => <p className="formatter-warning" key={item}>{item}</p>)}<pre className="latex-preview">{result.latex}</pre></> : <div className="empty-state"><strong>等待生成</strong><span>选择模板并提交后，这里会显示完整标准 LaTeX 源码。</span></div>}
    </section></div>
  </div>;
}
