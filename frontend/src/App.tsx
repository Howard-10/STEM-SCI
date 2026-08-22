import { useState } from "react";

import { AuditValidationPage } from "./pages/AuditValidationPage";
import { EvidenceLibraryPage } from "./pages/EvidenceLibraryPage";
import { ResearchCockpitPage } from "./pages/ResearchCockpitPage";
import { ResearchWorkflowPage } from "./pages/ResearchWorkflowPage";

export type WorkspaceTab = "cockpit" | "evidence" | "workflow" | "audit";

const tabs: Array<{ id: WorkspaceTab; label: string; short: string }> = [
  { id: "cockpit", label: "研究驾驶舱", short: "驾驶舱" },
  { id: "evidence", label: "证据库", short: "证据" },
  { id: "workflow", label: "研究流程", short: "流程" },
  { id: "audit", label: "审计与验证", short: "审计" },
];

export function App() {
  const [tab, setTab] = useState<WorkspaceTab>("cockpit");
  return <div className="app-shell"><header className="global-header"><a className="brand" href="#cockpit" onClick={() => setTab("cockpit")}><span className="brand-mark">S</span><span><strong>STEM-SCI</strong><small>Physics-STEM Research Workspace</small></span></a><nav className="workspace-nav" aria-label="研究工作区">{tabs.map((item) => <button className={tab === item.id ? "nav-active" : ""} key={item.id} onClick={() => setTab(item.id)} type="button"><span className="nav-full">{item.label}</span><span className="nav-short">{item.short}</span></button>)}</nav><span className="header-status"><i />研究环境</span></header><main className="page-frame">{tab === "cockpit" && <ResearchCockpitPage onNavigate={setTab} />}{tab === "evidence" && <EvidenceLibraryPage />}{tab === "workflow" && <ResearchWorkflowPage />}{tab === "audit" && <AuditValidationPage />}</main><nav className="mobile-nav" aria-label="移动端导航">{tabs.map((item) => <button className={tab === item.id ? "nav-active" : ""} key={item.id} onClick={() => setTab(item.id)} type="button">{item.short}</button>)}</nav></div>;
}
