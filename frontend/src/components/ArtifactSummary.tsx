import type { ResearchArtifact } from "../types/research";
import { TechnicalTrace } from "./TechnicalTrace";

export function ArtifactSummary({ artifacts }: { artifacts: ResearchArtifact[] }) { if (!artifacts.length) return <p className="empty-state">当前阶段尚未生成研究产物。</p>; return <div className="artifact-list">{artifacts.slice(-5).map((artifact, index) => <article className="artifact-item" key={`${artifact.kind}-${index}`}><span className="artifact-icon">▣</span><div><strong>{artifact.label}</strong><small>候选研究产物</small></div>{artifact.technicalRef && <TechnicalTrace><code>{artifact.technicalRef}</code></TechnicalTrace>}</article>)}</div>; }
