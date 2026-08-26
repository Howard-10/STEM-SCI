import type { EvidenceViewModel } from "../types/research";

export function CitationItem({ item, onOpen }: { item: EvidenceViewModel; onOpen?: () => void }) {
  return <button className="citation-item" onClick={onOpen} type="button"><div className="citation-heading"><strong>{item.title}</strong><span className={`status-dot status-${item.gateTone}`} /></div><p>{item.excerpt}</p><small>{item.source}{item.page ? ` · ${item.page}` : " · 定位待补充"}{item.pdfPath ? ` · ${item.pdfPath}` : ""} · {item.verification}</small></button>;
}
