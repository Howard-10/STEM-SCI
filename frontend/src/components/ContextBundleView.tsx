import type { Bundle } from "../types/context";

interface ContextBundleViewProps {
  bundle: Bundle | null;
  onBuild: () => void;
  ready: boolean;
}

export function ContextBundleView({ bundle, onBuild, ready }: ContextBundleViewProps) {
  return (
    <section>
      <h2>ContextBundle 构建与查看</h2>
      <button disabled={!ready} onClick={onBuild} type="button">构建 500-token ContextBundle</button>
      {bundle && <pre>{JSON.stringify(bundle, null, 2)}</pre>}
    </section>
  );
}
