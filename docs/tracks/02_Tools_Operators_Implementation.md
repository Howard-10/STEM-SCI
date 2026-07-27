# STEM-SCI 工具与 Operator 实施说明

> 技术线：工具
> 目标：把文献检索、数据处理、代码生成、执行、统计分析和导出封装为可替换、可审计、受权限控制的 Operator。
> 当前阶段：Phase 1 只实现契约、注册表、运行记录、Store 接口和安全边界。
> 核心原则：Operator 只执行动作，不做科研决策，不修改项目阶段。

---

## 1. 最终要解决的问题

1. 如何统一调用不同工具。
2. 如何记录输入、输出、环境、日志、成本和错误。
3. 如何替换 Codex、Python、SPSS 或检索工具而不影响 Controller。
4. 如何限制网络、时间、资源和权限。
5. 如何保证正式结果来自真实执行。
6. 如何让每次工具调用可追溯、可重试、可复现。

## 2. 负责范围

### 2.1 负责

- `OperatorSpec`、`OperatorRun`、`OperatorRegistry`。
- `ArtifactStore`、`ExecutionStore` 接口。
- `DataFreezeOperator`、`CodingProvider`、Python/SPSS、检索、学生代码和导出 Operator 的契约。
- 执行环境、日志、错误、超时、重试和权限描述。
- `PYTHON_ONLY` 与 `SPSS_PYTHON_DUAL` 模式策略。

### 2.2 不负责

- 不决定研究问题或统计方法。
- 不修改 `current_stage`。
- 不批准数据处理或分析计划。
- 不解释正式结果。
- 不直接写论文。
- Phase 1 不接真实 Codex、SPSS、GraphRAG 和任意代码执行。

## 3. 标准调用关系

```text
Agent 产生 ToolRequest
        ↓
Controller 权限检查
        ↓
OperatorRegistry 解析能力
        ↓
Operator 执行
        ↓
OperatorRun + ArtifactRef + ErrorEvent
        ↓
Controller 合并与路由
```

禁止：

```text
Agent → 直接执行 Shell
Agent → 直接写 Store
Operator → 修改 current_stage
Operator → 自行批准工件
```

## 4. 核心数据对象

### 4.1 OperatorSpec

```python
class OperatorSpec(BaseModel):
    operator_id: str
    operator_version: str
    display_name: str
    capability: str
    input_schema_ref: str
    output_schema_ref: str
    required_permissions: list[str]
    supported_artifact_types: list[str]
    estimated_cost: float | None
    timeout_seconds: int
    retry_policy: dict
    health_check_required: bool
```

### 4.2 OperatorRun

```python
class OperatorRun(BaseModel):
    operator_run_id: str
    operator_id: str
    operator_version: str
    request_ref: str
    input_artifact_refs: list[str]
    output_artifact_refs: list[str]
    environment_ref: str | None
    log_ref: str | None
    error_ref: str | None
    status: str
    started_at: datetime
    finished_at: datetime | None
```

### 4.3 ToolRequest

```python
class ToolRequest(BaseModel):
    request_id: str
    requested_capability: str
    input_refs: list[str]
    required_output_types: list[str]
    permission_scope: list[str]
    timeout_seconds: int | None
```

### 4.4 ArtifactRef

```python
class ArtifactRef(BaseModel):
    artifact_id: str
    artifact_type: str
    version: int
    content_uri: str
    sha256: str
    created_at: datetime
    created_by: str
    supersedes_ref: str | None
```

### 4.5 ExecutionEnvironmentRef

```python
class ExecutionEnvironmentRef(BaseModel):
    environment_id: str
    runtime: str
    runtime_version: str
    dependency_lock_hash: str | None
    operating_system: str
    container_image_digest: str | None
    random_seed: int | None
```

## 5. OperatorRegistry

```python
class OperatorRegistry:
    def register(self, spec: OperatorSpec, factory: Callable) -> None: ...
    def get_spec(self, operator_id: str) -> OperatorSpec: ...
    def resolve(self, capability: str) -> list[OperatorSpec]: ...
    def health(self, operator_id: str) -> bool: ...
```

必须支持：

- capability 查找。
- 多个可替换 Operator。
- 版本、权限、健康状态、超时和重试。
- 禁止调用未注册工具。

## 6. Store 接口

### 6.1 ArtifactStore

```python
class ArtifactStore(Protocol):
    def put(self, artifact: ArtifactRef) -> str: ...
    def get(self, artifact_id: str, version: int | None = None) -> ArtifactRef: ...
    def list_versions(self, artifact_id: str) -> list[ArtifactRef]: ...
    def mark_superseded(self, artifact_id: str, by_ref: str) -> None: ...
```

### 6.2 ExecutionStore

```python
class ExecutionStore(Protocol):
    def put_run(self, run: OperatorRun) -> str: ...
    def get_run(self, run_id: str) -> OperatorRun: ...
    def put_environment(self, env: ExecutionEnvironmentRef) -> str: ...
    def get_environment(self, environment_id: str) -> ExecutionEnvironmentRef: ...
```

工具组只实现 DecisionStore 的技术接口，不产生科研审批。

## 7. 主要 Operator 契约

### LiteratureSearchOperator

输入：`SearchProtocolRef`。
输出：搜索结果工件和 `OperatorRun`。

### DataAuditOperator

输入：`RawDatasetRef`、`DataDictionaryRef`。
输出：`DataAuditReportRef`。

### DataFreezeOperator

输入：`ProcessedDatasetRef`、`ApprovalRecordRef`。
输出：`FrozenDatasetRef`、`DataFreezeRecordRef`。

必须区分：

```text
requested_by = controller
executed_by = data_freeze_operator
```

### CodingProviderOperator

输入：`CodeSpecificationRef`。
输出：`CodeArtifactRef`。
Codex 只是一个可替换 Provider。

### PythonAnalysisOperator / SPSSOperator

输入：`CodeArtifactRef`、`FrozenDatasetRef`、环境引用。
输出：`ExecutionRunRef`、原始结果工件。

### LearnerCodeExecutionOperator

后续在 `LearnerCodeSandbox` 中运行学生代码。

### ProvenanceExportOperator

输出复现包、工件清单、WorkflowSignature 和溯源图。

## 8. 数据版本链

```text
RawDataset
→ DataAudit
→ ProcessedDataset
→ Human Approval
→ FrozenDataset
```

规则：

- RawDataset 只读。
- ProcessedDataset 必须关联处理计划。
- FrozenDataset 必须关联 ApprovalRecord。
- FrozenDataset 不可修改。
- 正式 ExecutionRun 只能读取 FrozenDataset。
- 数据和 Schema 都必须有哈希。

## 9. 执行模式

```python
class AnalysisMode(str, Enum):
    PYTHON_ONLY = "PYTHON_ONLY"
    SPSS_PYTHON_DUAL = "SPSS_PYTHON_DUAL"
```

- `PYTHON_ONLY` 可达到 `execution_verified`，不能达到 `cross_engine_verified`。
- `SPSS_PYTHON_DUAL` 经独立复核后才能达到 `cross_engine_verified`。

## 10. Phase 1 实施步骤

1. 实现 `OperatorSpec` 和 `OperatorRun`。
2. 实现 `OperatorRegistry`。
3. 实现 `ArtifactStore`、`ExecutionStore` 接口。
4. 实现 Raw/Processed/Frozen、DataFreezeRecord。
5. 实现 CodeSpecification、CodeArtifact、ExecutionRun。
6. 实现 ResultValidationReport、StatisticalResultCard。
7. 实现 `mode_policy`。
8. 编写不变量测试和示例。

## 11. 必须测试

1. OperatorRun 不能修改 `current_stage`。
2. 未注册 Operator 不能执行。
3. 正式 ExecutionRun 不能读取 RawDataset 或 ProcessedDataset。
4. 正式 ExecutionRun 可以读取 FrozenDataset。
5. DataFreezeRecord 必须有 ApprovalRecordRef。
6. `PYTHON_ONLY` 不能标记 `cross_engine_verified`。
7. ArtifactRef 必须有 SHA256。
8. 更新不能覆盖旧版本。
9. Operator 失败只能产生 Run 级错误，不能自动阻塞 Project。

## 12. Phase 1 交付物

```text
OperatorSpec / OperatorRun / OperatorRegistry
ArtifactRef / ExecutionEnvironmentRef
ArtifactStore / ExecutionStore 接口
Raw / Processed / Frozen 模型
DataFreezeRecord
CodeSpecification / CodeArtifact / ExecutionRun
ResultValidationReport / StatisticalResultCard
AnalysisModePolicy
测试、README、示例
```

## 13. 完成定义

- Operator 能按 capability 注册和解析。
- 每次执行都有 OperatorRun。
- Operator 无状态推进权。
- 工件有版本、哈希和环境引用。
- 正式执行只接受 FrozenDataset。
- 模式约束正确。
- Store 接口稳定。
- Phase 1 不接真实外部服务。

## 14. 后续阶段

- Phase 2：数据导入、审计、冻结和 PYTHON_ONLY 最小分析。
- Phase 4：学生代码执行和 Feedback 工具。
- Phase 5：真实文献搜索与解析。
- Phase 6：Codex、SPSS、Python 双引擎复核。

## 15. 验收问题

1. 每次真实操作是否都有 OperatorRun？
2. 工具是否能替换而不改变 Controller？
3. 工具是否可能越权？
4. 正式分析是否只读 FrozenDataset？
5. 工件是否有版本、哈希和环境？
