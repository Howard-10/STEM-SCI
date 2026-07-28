import type { Source, SourceChunk } from "../types/context";

interface SourceLibraryProps {
  chunks: SourceChunk[];
  onSelect: (sourceId: string) => void;
  onUpload: (file: File) => void;
  selectedSource?: Source | null;
  sources: Source[];
}

export function SourceLibrary({ chunks, onSelect, onUpload, selectedSource, sources }: SourceLibraryProps) {
  return (
    <section>
      <h2>来源资料库</h2>
      <label>
        导入 Markdown、TXT、JSON 或可提取文本的 PDF
        <input accept=".md,.txt,.json,.pdf,application/pdf" onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onUpload(file);
        }} type="file" />
      </label>
      <ul>
        {sources.map((source) => (
          <li key={source.source_id}>
            <button onClick={() => onSelect(source.source_id)} type="button">
              {source.filename}
            </button>
            <small> {source.verification_status} · {source.sha256.slice(0, 12)}</small>
          </li>
        ))}
      </ul>
      {selectedSource && (
        <article>
          <h3>{selectedSource.filename}</h3>
          <p>来源 ID：{selectedSource.source_id}</p>
          <p>Chunk 数：{chunks.length}</p>
          <ul>{chunks.map((chunk) => <li key={chunk.chunk_id}>{chunk.chunk_id} · {chunk.location.heading ?? "无标题"}</li>)}</ul>
        </article>
      )}
    </section>
  );
}
