import { useEffect, useState } from "react";

import { api } from "../api/client";
import { ContextBundleView } from "../components/ContextBundleView";
import { EvidenceDetailView } from "../components/EvidenceDetailView";
import { EvidenceSearch } from "../components/EvidenceSearch";
import { SourceLibrary } from "../components/SourceLibrary";
import { SharedCorpusRetrieval } from "../components/SharedCorpusRetrieval";
import type {
  Bundle,
  EvidenceDetail,
  SearchResult,
  SharedContextMode,
  SharedCorpusSummary,
  SharedRetrievalResponse,
  Source,
  SourceChunk,
} from "../types/context";

const defaultProjectId = import.meta.env.VITE_PROJECT_ID ?? "demo";

export function ContextWorkspacePage() {
  const [projectId, setProjectId] = useState(defaultProjectId);
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [chunks, setChunks] = useState<SourceChunk[]>([]);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [detail, setDetail] = useState<EvidenceDetail | null>(null);
  const [sourceChunk, setSourceChunk] = useState<SourceChunk | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [sharedBundle, setSharedBundle] = useState<Bundle | null>(null);
  const [sharedCorpus, setSharedCorpus] = useState<SharedCorpusSummary | null>(null);
  const [sharedMode, setSharedMode] = useState<SharedContextMode>("discovery");
  const [sharedResult, setSharedResult] = useState<SharedRetrievalResponse | null>(null);
  const [error, setError] = useState("");

  const run = async (work: () => Promise<void>) => {
    try {
      setError("");
      await work();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "请求失败");
    }
  };

  const refreshSources = async () => setSources(await api.listSources(projectId));

  useEffect(() => {
    void run(refreshSources);
  }, [projectId]);

  useEffect(() => {
    void run(async () => {
      const corpora = await api.listSharedCorpora();
      setSharedCorpus(corpora.find((corpus) => corpus.corpus_id === "physics_stem_v1") ?? null);
    });
  }, []);

  const selectSource = (sourceId: string) => run(async () => {
    const [source, sourceChunks] = await Promise.all([
      api.getSource(projectId, sourceId),
      api.getChunks(projectId, sourceId),
    ]);
    setSelectedSource(source);
    setChunks(sourceChunks);
  });

  const openEvidence = (evidenceId: string) => run(async () => {
    const evidence = await api.getEvidence(projectId, evidenceId);
    setDetail(evidence);
    const sourceChunks = await api.getChunks(projectId, evidence.source_id);
    setSourceChunk(sourceChunks.find((chunk) => chunk.chunk_id === evidence.chunk_id) ?? null);
  });

  const search = (queryText: string) => run(async () => setResults(await api.search(projectId, queryText)));

  return (
    <main>
      <h1>STEM-SCI Context MVP</h1>
      <label>
        项目 ID
        <input onChange={(event) => setProjectId(event.target.value)} value={projectId} />
      </label>
      <SourceLibrary
        chunks={chunks}
        onSelect={selectSource}
        onUpload={(file) => void run(async () => { await api.importSource(projectId, file); await refreshSources(); })}
        selectedSource={selectedSource}
        sources={sources}
      />
      <EvidenceSearch onOpen={openEvidence} onSearch={search} query={query} results={results} setQuery={setQuery} />
      <EvidenceDetailView
        detail={detail}
        onVerify={(evidenceId) => void run(async () => {
          await api.verifySource(projectId, evidenceId, "frontend-user", "source checked in Context MVP");
          await openEvidence(evidenceId);
          if (query.trim()) await search(query);
        })}
        sourceChunk={sourceChunk}
      />
      <ContextBundleView
        bundle={bundle}
        onBuild={() => void run(async () => setBundle(await api.buildBundle(projectId, query, 500)))}
        ready={Boolean(query.trim())}
      />
      <SharedCorpusRetrieval
        bundle={sharedBundle}
        corpus={sharedCorpus}
        mode={sharedMode}
        onBuild={() => void run(async () => {
          setSharedBundle(await api.buildSharedBundle(projectId, query, sharedMode));
        })}
        onModeChange={setSharedMode}
        onSearch={() => void run(async () => {
          setSharedResult(await api.searchSharedCorpus(projectId, query, sharedMode));
        })}
        ready={Boolean(query.trim())}
        result={sharedResult}
      />
      {error && <p role="alert">{error}</p>}
    </main>
  );
}
