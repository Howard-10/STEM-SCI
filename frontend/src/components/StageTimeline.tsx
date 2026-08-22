import type { ResearchContextViewModel, ResearchStage } from "../types/research";
import { stageDefinitions } from "../utils/researchViewModel";

const statusLabel = { current: "进行中", complete: "已完成", waiting: "等待人工", rework: "需要返工", blocked: "已阻断", failed: "执行失败" } as const;

export function StageTimeline({ context, onSelect, selected }: { context: ResearchContextViewModel; onSelect?: (stage: ResearchStage) => void; selected?: ResearchStage }) {
  const currentIndex = stageDefinitions.findIndex((stage) => stage.id === context.stage);
  return <div className="stage-timeline">{stageDefinitions.map((stage, index) => { const state = index < currentIndex ? "complete" : stage.id === context.stage ? context.stageStatus : "upcoming"; return <button className={`timeline-stage timeline-${state} ${selected === stage.id ? "timeline-selected" : ""}`} key={stage.id} onClick={() => onSelect?.(stage.id)} type="button"><span className="timeline-marker">{index < currentIndex ? "✓" : String(index + 1).padStart(2, "0")}</span><span><strong>{stage.label}</strong><small>{state === "upcoming" ? "待进入" : statusLabel[state as keyof typeof statusLabel]}</small></span></button>; })}</div>;
}
