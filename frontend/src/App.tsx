import { useState } from "react";

import { ContextWorkspacePage } from "./pages/ContextWorkspacePage";
import { WorkflowWorkspacePage } from "./pages/WorkflowWorkspacePage";

type WorkspaceTab = "workflow" | "context";

export function App() {
  const [tab, setTab] = useState<WorkspaceTab>("workflow");

  return (
    <>
      <nav className="workspace-nav" aria-label="工作台模块">
        <button className={tab === "workflow" ? "nav-active" : ""} onClick={() => setTab("workflow")}>
          研究流程
        </button>
        <button className={tab === "context" ? "nav-active" : ""} onClick={() => setTab("context")}>
          证据与上下文
        </button>
      </nav>
      {tab === "workflow" ? <WorkflowWorkspacePage /> : <ContextWorkspacePage />}
    </>
  );
}
