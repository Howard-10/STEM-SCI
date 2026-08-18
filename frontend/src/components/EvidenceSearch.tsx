import type { SearchResult } from "../types/context";

interface EvidenceSearchProps {
  onOpen: (evidenceId: string) => void;
  onSearch: (query: string) => void;
  query: string;
  results: SearchResult[];
  setQuery: (query: string) => void;
}

export function EvidenceSearch({ onOpen, onSearch, query, results, setQuery }: EvidenceSearchProps) {
  return (
    <section>
      <h2>证据检索</h2>
      <input onChange={(event) => setQuery(event.target.value)} placeholder="关键词" value={query} />
      <button disabled={!query.trim()} onClick={() => onSearch(query)} type="button">检索</button>
      <ul>
        {results.map(({ evidence, score }) => (
          <li key={evidence.evidence_id}>
            <blockquote>{evidence.excerpt}</blockquote>
            <small>{evidence.verification_status} · score {score} · {evidence.chunk_id}</small>
            <button onClick={() => onOpen(evidence.evidence_id)} type="button">打开详情</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
