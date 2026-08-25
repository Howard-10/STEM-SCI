import type {
  Bundle,
  SharedContextMode,
  SharedCorpusSummary,
  SharedRetrievalResponse,
} from "../types/context";

interface SharedCorpusRetrievalProps {
  bundle: Bundle | null;
  corpus: SharedCorpusSummary | null;
  mode: SharedContextMode;
  onBuild: () => void;
  onModeChange: (mode: SharedContextMode) => void;
  onSearch: () => void;
  ready: boolean;
  result: SharedRetrievalResponse | null;
}

export function SharedCorpusRetrieval({
  bundle,
  corpus,
  mode,
  onBuild,
  onModeChange,
  onSearch,
  ready,
  result,
}: SharedCorpusRetrievalProps) {
  const formalLocked = corpus !== null && !corpus.formal_evidence_ready;

  return (
    <section aria-labelledby="shared-corpus-heading">
      <h2 id="shared-corpus-heading">Physics-STEM 共享知识库检索</h2>
      <p>
        图谱只用于候选论文导航；返回的原文片段才是待核验材料。当前共享图谱三元组均为
        <code>model_generated_unverified</code>，不能直接作为正式科研结论。
      </p>
      {corpus ? (
        <p>
          语料：{corpus.paper_count} 篇论文、{corpus.vector_chunk_count} 个文本切片。发现模式：
          {corpus.discovery_ready ? "可用" : "不可用"}；正式证据模式：
          {corpus.formal_evidence_ready ? "可用" : "暂时锁定"}。
        </p>
      ) : <p>正在读取共享语料状态。</p>}
      <label>
        使用模式
        <select onChange={(event) => onModeChange(event.target.value as SharedContextMode)} value={mode}>
          <option value="discovery">发现模式：允许未核验候选，不能写入正式结论</option>
          <option disabled={formalLocked} value="formal">正式证据模式：仅可引用已定位、已核验原文</option>
        </select>
      </label>
      {formalLocked && <p className="warning-text">正式模式被安全锁定：尚缺“切片 → PDF 页码/字符定位索引”和来源核验。</p>}
      <div className="button-row">
        <button className="secondary-action" disabled={!ready || (mode === "formal" && formalLocked)} onClick={onSearch} type="button">
          检索共享语料
        </button>
        <button className="primary-action" disabled={!ready || (mode === "formal" && formalLocked)} onClick={onBuild} type="button">
          构建共享 ContextBundle
        </button>
      </div>
      {result && (
        <>
          <p>
            实际检索模式：<strong>{result.retrieval_trace.retrieval_mode}</strong>；状态：
            <strong>{result.retrieval_status}</strong>。图候选 {result.candidate_papers.length} 篇，原文命中 {result.chunk_hits.length} 条。
          </p>
          {result.risk_flags.length > 0 && <p className="warning-text">限制：{result.risk_flags.join("；")}</p>}
          <h3>图导航候选论文</h3>
          <ul>
            {result.candidate_papers.slice(0, 5).map((candidate) => (
              <li key={candidate.canonical_paper_id}>
                {candidate.graph_paper_id}：{candidate.matched_facets.join("；")}
              </li>
            ))}
          </ul>
          <h3>原文切片命中</h3>
          <ul>
            {result.chunk_hits.map((hit) => (
              <li key={hit.canonical_chunk_id}>
                <strong>{hit.paper_title}</strong>（{hit.section_hint ?? "未标记章节"}）
                <blockquote>{hit.excerpt}</blockquote>
                <small>{hit.retrieval_modalities.join(" + ") || "文本检索"}；定位：{hit.locator_status}</small>
              </li>
            ))}
          </ul>
        </>
      )}
      {bundle && bundle.retrieval_strategy === "hybrid" && (
        <details>
          <summary>查看本次共享 ContextBundle 的追溯信息</summary>
          <pre>{JSON.stringify(bundle, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}
