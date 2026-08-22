import type { EvidenceCoverage as Coverage } from "../types/research";

export function EvidenceCoverage({ coverage }: { coverage: Coverage }) {
  if (!coverage.claimLevelAvailable) return <div className="coverage coverage-partial"><div><span>证据充分度</span><strong>未提供 claim-level 数据</strong></div><small>{coverage.supportedClaims ? `${coverage.supportedClaims} 条有来源支持，${coverage.verifiedClaims} 条已核验` : "当前没有可计入的核心证据"}</small></div>;
  return <div className={`coverage coverage-${coverage.coverageStatus}`}><div><span>证据充分度</span><strong>有来源支持：{coverage.supportedClaims} / {coverage.totalClaims}</strong></div><div className="coverage-stats"><span>已核验：{coverage.verifiedClaims} / {coverage.totalClaims}</span><span>{coverage.unsupportedClaims} 项待补充证据</span></div></div>;
}
