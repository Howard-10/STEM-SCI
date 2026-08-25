import { useState } from "react";
import { App } from "./App";
import { LatexFormatterPage } from "./pages/LatexFormatterPage";

export function AppShell() {
  const [open, setOpen] = useState(false);
  const projectId = import.meta.env.VITE_PROJECT_ID && import.meta.env.VITE_PROJECT_ID !== "demo"
    ? import.meta.env.VITE_PROJECT_ID
    : "physics-ai-demo";

  return <>
    <App />
    <button className="latex-launch-button" type="button" onClick={() => setOpen(true)}>
      投稿格式化 / LaTeX
    </button>
    {open && <div className="latex-modal" role="dialog" aria-modal="true" aria-label="投稿格式化">
      <button className="latex-close-button" type="button" onClick={() => setOpen(false)}>关闭</button>
      <LatexFormatterPage projectId={projectId} />
    </div>}
  </>;
}
