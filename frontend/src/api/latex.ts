export type LatexTemplate = { template_id: string; name: string; venue_type: "journal" | "conference" | "generic"; publisher: string; description: string; version: string; source_url: string | null; official_status: "official" | "community" | "generic"; document_class: string; supports_bibliography: boolean };
export type LatexResponse = { template: LatexTemplate; latex: string; sha256: string; validation_errors: string[]; validation_warnings: string[]; compile: { status: "compiled" | "skipped" | "failed"; engine: string | null; pdf_available: boolean; log: string; errors: string[]; warnings: string[] } };

// Prefer an explicit backend URL; otherwise use the current host so localhost and 127.0.0.1 stay consistent.
const base = (import.meta.env.VITE_API_BASE_URL || `${window.location.origin}/api/v1`).replace(/\/$/, "");

export async function listLatexTemplates(): Promise<LatexTemplate[]> {
  try {
    const response = await fetch(`${base}/latex/templates`);
    if (!response.ok) throw new Error(`模板接口返回 HTTP ${response.status}`);
    return response.json() as Promise<LatexTemplate[]>;
  } catch (error) {
    if (error instanceof TypeError) throw new Error(`无法连接模板接口：${base}/latex/templates`);
    throw error;
  }
}

export async function generateLatex(input: { template_id: string; title: string; authors: string[]; abstract: string; content: string; keywords: string[]; bibliography: string; compile_pdf: boolean }): Promise<LatexResponse> {
  const response = await fetch(`${base}/latex/generate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input) });
  const payload = await response.json() as { error?: { message?: string } };
  if (!response.ok) throw new Error(payload.error?.message ?? `LaTeX 接口返回 HTTP ${response.status}`);
  return payload as LatexResponse;
}
