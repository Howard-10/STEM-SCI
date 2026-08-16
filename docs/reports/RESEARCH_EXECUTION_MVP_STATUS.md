# 科研代码与统计执行 MVP：实现状态

更新时间：2026-08-11

## 已经跑通的正式最小链路

本轮实现的是受 Controller 调用的确定性执行路径，而不是让科研数据分析 Agent 自己分析数据：

```text
FrozenDataset
→ ExecutableAnalysisPlan
→ CodeSpecification
→ CodeArtifact
→ CodeReviewGate
→ ResearchCodeSandbox
→ ExecutionRun
→ ResultValidationReport
→ StatisticalResultCard
```

数据分析 Agent 仍仅提出 `ExecutableAnalysisPlanCandidate`、`CodeSpecificationDraft`、诊断建议和解释边界；它没有获得改数据、冻结数据、执行 Python/SPSS 或生成统计数值的权限。

## 真实运行证据

使用仓库中的合成 `demo_seed` CSV 运行了 `group_mean_difference` 示例。它是教学/工程验收数据，**不是对真实学生的研究结论**。

| 检查项 | 实际结果 |
| --- | --- |
| 代码审查闸门 | `PASS` |
| Python 代码工件运行 | `SUCCEEDED` |
| 验证模式 | `SINGLE_ENGINE` |
| 验证结果 | `passed=true` |
| Result Card 状态 | `execution_verified` |
| 样本量 | 6 |
| 两组迁移得分均值 | 77.67 与 62.33 |
| 第二排序组减第一排序组的均值差 | -15.33 |

数值由冻结 CSV 的实际执行输出解析而来；Agent 和 Codex 都不允许直接填写这些数字。

## Codex 的接入边界

`CodexCliCodingProvider` 已作为可替换的 CodingProvider 接口实现，调用方式采用官方的非交互 `codex exec` 思路，并固定为只读沙箱参数。它只接收不含数据行的 `CodeSpecification`，只能返回候选 `CodeArtifact`。

- 本机当前检测到 Codex 桌面程序文件，但 PowerShell 无法直接执行该文件；因此 Provider 会 fail-closed，记录不可用而不是假装代码已生成。
- 目前可执行的验收链路使用 `DeterministicTemplateCodingProvider` 生成受检查的固定 Python 模板，目的是验证整个工件、审查和执行路径。
- 非模板的 Codex 输出即使通过静态扫描，也必须人工批准后才能送入执行沙箱。
- Codex 不拥有研究设计、统计模型、数据版本、结果数字或项目阶段的决定权。

官方 Codex 文档说明 `codex exec` 用于非交互式工作流，且可显式设置沙箱/审批策略；生产接入前仍需完成本机 CLI 认证与可执行性验证。

## SPSS 的接入边界

以下部件已经具备并被测试：

- `SpssSyntaxSpecificationCompiler`：将双引擎的 ExecutableAnalysisPlan 编译为带 FrozenDataset 哈希和 CSV Schema 的 SPSS 语法规格；
- `SpssSyntaxTemplateProvider`：生成可审查的 `.sps` 模板；
- `SpssAdapter`：仅在检测到批处理 SPSS 后运行语法、保存日志/输出并标准化两组聚合结果；
- `CrossEngineResultValidator`：要求两引擎运行成功、结果键集合相同且数值在预设容差内，才生成 `CROSS_ENGINE` 报告。

当前电脑未检测到可用 IBM SPSS Statistics 批处理程序。因此真实运行只能是：

```text
PYTHON_ONLY → SINGLE_ENGINE → execution_verified
```

这不是 SPSS + Python 双轨验证，也不会标记为 `cross_engine_verified`。如果正式研究预注册选择 `SPSS_PYTHON_DUAL`，而运行环境没有 SPSS，系统会阻止该双轨 Run；不能私自降级并继续声称双轨验证。

## 安全与可复现限制

本轮 ResearchCodeSandbox 已限制代码工件进入独立 Run 目录、冻结数据哈希核验、最小环境变量、静态禁用网络/系统命令相关导入、禁止依赖安装、限制结果文件大小并强制超时。

当前 Docker 守护进程未启动，因此它是 `development_restricted` 的本地开发沙箱，尚未达到容器级 CPU、内存和宿主文件系统隔离。正式处理真实研究数据之前，必须启用容器运行器或等价的操作系统级隔离。

## 已验证的负向场景

1. FrozenDataset 文件被篡改：在运行前被阻塞；
2. 代码包含 `socket` 等网络能力：CodeReviewGate 阻塞，沙箱不启动；
3. 不存在 Codex CLI：Provider 抛出明确不可用状态，不回退成“Codex 已运行”；
4. 不存在 SPSS：SPSS Run 标记 `BLOCKED`，不生成双引擎结果；
5. 双引擎结果键集合不一致或数值超容差：CrossEngineResultValidator 不能通过。

## 下一步的真实前置条件

1. 启动 Docker 并完成容器镜像/资源限制配置，将开发沙箱替换为容器化 ResearchCodeSandbox；
2. 安装并许可 IBM SPSS Statistics，设置 `STEM_SCI_SPSS_EXECUTABLE` 后运行同一份合成数据的双引擎验收；
3. 配置可运行、已认证的 Codex CLI，先让它生成候选代码并走“代码审查 + 人工批准 + 沙箱”路径；
4. 再扩展真实研究所需模型。当前真实执行模板只支持两组 CSV 描述性均值比较，框架的 `AnalysisModelSpecification` 可以扩展，但不能把线性混合模型等复杂方法伪装为已经可运行。
