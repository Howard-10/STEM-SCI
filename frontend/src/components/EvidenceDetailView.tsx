import type { EvidenceDetail, SourceChunk } from "../types/context";

interface EvidenceDetailViewProps {
  detail: EvidenceDetail | null;
  onVerify: (evidenceId: string) => void;
  sourceChunk: SourceChunk | null;
}

export function EvidenceDetailView({ detail, onVerify, sourceChunk }: EvidenceDetailViewProps) {
  if (!detail) return <section><h2>Evidence 详情</h2><p>从检索结果中打开一条 Evidence。</p></section>;
  return (
    <section>
      <h2>Evidence 详情</h2>
      <p>{detail.evidence_id} · {detail.verification_status}</p>
      <blockquote>{detail.excerpt}</blockquote>
      <p>来源 {detail.source_id}，Chunk {detail.chunk_id}</p>
      <p>核验人：{detail.verified_by ?? "未核验"}</p>
      <button onClick={() => onVerify(detail.evidence_id)} type="button">标记 source_verified</button>
      {sourceChunk && <details><summary>反查 SourceChunk</summary><pre>{sourceChunk.text}</pre></details>}
    </section>
  );
}
