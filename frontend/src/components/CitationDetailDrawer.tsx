import type { EvidenceViewModel } from "../types/research";
import { GateBadge } from "./GateBadge";

export function CitationDetailDrawer({ item, onClose }: { item: EvidenceViewModel | null; onClose: () => void }) {
  if (!item) return null;
  return <div className="drawer-backdrop" role="presentation" onClick={onClose}><aside className="citation-drawer" onClick={(event) => event.stopPropagation()} aria-label="证据详情"><div className="drawer-heading"><div><span className="eyebrow">EVIDENCE DETAIL</span><h2>{item.title}</h2></div><button className="icon-button" onClick={onClose} type="button" aria-label="关闭">×</button></div><GateBadge gate={{ kind: "evidence", label: "Evidence Gate", tone: item.gateTone, detail: item.verification }} /><blockquote>{item.excerpt}</blockquote><dl className="detail-list"><div><dt>来源</dt><dd>{item.source}</dd></div><div><dt>PDF 位置</dt><dd>{item.pdfPath ?? "尚无 PDF 路径"}</dd></div><div><dt>DOI</dt><dd>{item.doi ?? "未提供"}</dd></div><div><dt>定位</dt><dd>{item.page ?? "尚无页码定位"}</dd></div><div><dt>引用资格</dt><dd>{item.verification}</dd></div></dl>{item.gateTone !== "verified" && <p className="warning-text">这条材料可以支持探索，但尚未通过正式 Evidence Gate。</p>}<details className="technical-trace"><summary>技术追溯</summary><code>{item.technicalRef ?? "未提供"}</code></details></aside></div>;
}
