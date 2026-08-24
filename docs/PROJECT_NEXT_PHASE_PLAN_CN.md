# STEM-SCI 后续开发与部署计划

更新时间：2026-08-23

## 1. 先明确目标

当前项目已经有：

- Physics-STEM 共享论文库
- BM25、FAISS、图谱导航和混合检索
- `/api/v1/qa/answer` 对话问答链
- 六 Agent Controller 工作流
- 人工审批、REWORK、审计和 SQLite 持久化
- 本地数据流水线和研究执行接口
- 前端研究对话首页

下一阶段的目标不是继续堆零散功能，而是形成下面这条完整用户链路：

```text
注册/登录
→ 创建论文研究项目
→ 上传或编辑自己的论文材料
→ 私有论文材料解析、切片、索引
→ 对话提问
→ 共享论文库 + 用户私有论文库联合检索
→ 返回回答、证据、原文摘录和风险
→ 调用六 Agent 生成下一步研究建议
→ 经过人工审批后执行工作流
→ 使用 Codex 生成候选代码
→ 人工批准后执行分析
→ 结果验证、论文审查、版本化保存
→ 部署为评委可访问的稳定 Demo
```

## 2. 先分清三个概念

### 2.1 用户自己的“论文项目”

建议将平台中的核心对象定义为 `ResearchProject`，而不是直接把所有东西叫作“论文”。

一个项目可以包含：

- 论文题目和研究方向
- 研究问题
- 上传的参考文献
- 正在编辑的论文草稿
- 数据集和分析计划
- 对话记录
- Agent 工件
- 审批和审计记录

这样以后一个用户可以同时管理多篇论文，前端首页就可以先显示“我的研究项目”，点击某个项目进入工作区。

### 2.2 共享知识库和私有知识库

必须保持两条检索边界：

```text
共享 Physics-STEM 论文库
用户/项目私有论文材料
```

最终问答可以联合检索，但每条结果必须带：

- `project_id`
- `source_id`
- `document_id`
- `chunk_id`
- `source_scope`: `shared` 或 `private`
- `verification_status`

用户 A 不能检索到用户 B 的论文内容。这个隔离必须由后端查询条件和数据库约束保证，不能只依赖前端传参。

### 2.3 对话记忆和论文知识

二者不能混为一个“大文本记忆”：

```text
对话记忆：用户说过什么
项目记忆：研究方向、已批准决策、研究问题、约束条件
论文知识：论文正文、参考文献、原文切片和证据
```

论文正文应当保存为版本化文档和可检索 chunk，不应该直接全部塞进长期记忆。

## 3. 数据库和存储方案

### 3.1 推荐方案

比赛 Demo 和后续公网部署建议采用：

```text
PostgreSQL      用户、项目、权限、文档元数据、对话、记忆、工作流索引
对象存储        PDF、DOCX、CSV、论文草稿、代码和运行产物
现有 FAISS/BM25 私有或共享检索索引
Neo4j           共享论文关系图和图谱导航
SQLite          仅保留为本地开发或轻量工作流缓存
```

PostgreSQL 负责业务主数据，Neo4j 继续负责论文之间的关系导航。Neo4j 适合表达论文、作者、主题和引用关系；它不适合替代用户、权限、订单式业务数据的主数据库。

### 3.2 为什么不继续只用 SQLite

SQLite 适合当前单机 Demo，但用户登录、项目隔离、并发访问、会话、文档版本和权限增长以后，所有数据都挤在本地 SQLite 会带来：

- 并发写入能力有限
- 公网多进程部署不方便
- 备份和迁移边界不清晰
- 权限隔离主要靠代码实现
- 后续扩展任务队列和多实例困难

因此建议：

- 本地开发：SQLite 可以继续用。
- 第一版公网 Demo：PostgreSQL。
- 不要在当前阶段立刻把所有已有 SQLite 表一次性重写，先新增 Repository/Store 抽象，再逐步迁移。

### 3.3 论文文件放哪里

论文原文件、CSV 和生成的 DOCX 不建议直接存 PostgreSQL 字段中：

```text
数据库：文件元数据、哈希、版本、所有者、存储引用
对象存储：真正的 PDF/DOCX/CSV 文件
```

本地可以先用：

```text
storage/projects/{project_id}/documents/{document_id}/versions/{version}/
```

公网部署再替换为 S3 兼容对象存储或 MinIO，不改变上层接口。

### 3.4 向量索引怎么选

第一阶段不要同时引入很多新基础设施：

1. 共享语料继续使用现在的 BM25、FAISS 和 Neo4j。
2. 用户私有论文先使用“每个项目一个索引目录”的 FAISS + BM25。
3. 当项目数量和并发明显增加，再迁移到 Qdrant、pgvector 或专用向量服务。

关键不是先换向量数据库，而是先把 `project_id`、`document_id`、`chunk_id` 和权限过滤设计正确。

## 4. 后端后续接口安排

### P0：用户和项目基础接口

这一阶段是前后端能够真正做“我的论文管理”的前提。

```text
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/auth/me

GET    /api/v1/projects
POST   /api/v1/projects
GET    /api/v1/projects/{project_id}
PATCH  /api/v1/projects/{project_id}
DELETE /api/v1/projects/{project_id}
```

最小数据表：

```text
users
user_sessions
research_projects
project_members
```

安全要求：

- 密码只保存哈希，不保存明文。
- 登录后返回短期 access token 和可撤销 refresh token。
- 每个项目接口从 token 获取用户身份。
- 不信任前端直接传来的 `user_id`。
- 所有项目查询都必须同时检查项目成员关系。

比赛 Demo 第一版可以先实现邮箱/用户名 + 密码登录；第三方 OAuth 放到第二阶段。

### P0：论文和文档管理接口

建议把“论文正文”和“参考资料”都建模为 `ProjectDocument`，用 `document_type` 区分。

```text
GET    /api/v1/projects/{project_id}/documents
POST   /api/v1/projects/{project_id}/documents
GET    /api/v1/projects/{project_id}/documents/{document_id}
PATCH  /api/v1/projects/{project_id}/documents/{document_id}
DELETE /api/v1/projects/{project_id}/documents/{document_id}

POST   /api/v1/projects/{project_id}/documents/import
GET    /api/v1/projects/{project_id}/documents/{document_id}/versions
POST   /api/v1/projects/{project_id}/documents/{document_id}/versions
GET    /api/v1/projects/{project_id}/documents/{document_id}/versions/{version}
```

建议字段：

```text
document_id
project_id
owner_id
title
document_type       manuscript / reference / dataset / protocol
format              markdown / docx / pdf / csv
current_version
storage_ref
sha256
created_at
updated_at
```

在线编辑必须采用版本化保存：

```text
用户编辑
→ 创建新版本
→ 保存版本哈希
→ 记录修改人和时间
→ 可回滚到旧版本
```

不要直接覆盖原始论文文件。

### P0：项目私有检索和对话接口

现有接口可以保留，但需要加上登录身份和项目权限：

```text
POST /api/v1/qa/answer
POST /api/v1/retrieval/search
POST /api/v1/context/hybrid-build
```

建议增加更清晰的项目化别名：

```text
GET  /api/v1/projects/{project_id}/conversations
POST /api/v1/projects/{project_id}/conversations
GET  /api/v1/projects/{project_id}/conversations/{conversation_id}
POST /api/v1/projects/{project_id}/chat/answer
```

内部仍然可以复用当前 `QuestionAnswerService`，不需要立即重写问答核心。

问答检索链应该变为：

```text
用户问题
→ 查询改写
→ 项目权限检查
→ 共享论文检索
→ 当前项目私有论文检索
→ 项目记忆读取
→ Evidence Gate
→ LLM 工具路由
→ 回答和引用
→ 保存本轮记忆
```

### P1：论文解析和索引接口

```text
POST /api/v1/projects/{project_id}/documents/{document_id}/index
GET  /api/v1/projects/{project_id}/index-runs
GET  /api/v1/projects/{project_id}/index-runs/{run_id}
POST /api/v1/projects/{project_id}/documents/{document_id}/reindex
```

解析流程：

```text
文件上传
→ 文本解析
→ 页面/章节定位
→ canonical chunk
→ BM25 索引
→ 向量索引
→ 可选实体和关系抽取
→ 标记索引状态
```

索引状态建议：

```text
PENDING
PROCESSING
READY
FAILED
NEEDS_REVIEW
```

### P1：项目记忆接口

```text
GET    /api/v1/projects/{project_id}/memory
POST   /api/v1/projects/{project_id}/memory/entries
PATCH  /api/v1/projects/{project_id}/memory/entries/{memory_id}
DELETE /api/v1/projects/{project_id}/memory/entries/{memory_id}
POST   /api/v1/projects/{project_id}/memory/compact
```

记忆条目建议分为：

```text
conversation_summary
research_intent
research_question
approved_decision
user_preference
unresolved_question
evidence_summary
```

每条记忆都应带：

- `project_id`
- `created_by`
- `source_conversation_id`
- `source_artifact_refs`
- `confidence`
- `memory_status`
- `expires_at` 或版本信息

模型生成的记忆不能自动变成“事实”。建议状态：

```text
CANDIDATE
CONFIRMED
SUPERSEDED
DELETED
```

### P1：Agent 工具路由接口

当前 QA 已经有工具路由基础，下一步应把工具做成明确的后端注册表：

```text
GET  /api/v1/tools
POST /api/v1/projects/{project_id}/tool-runs
GET  /api/v1/projects/{project_id}/tool-runs
GET  /api/v1/projects/{project_id}/tool-runs/{run_id}
```

第一批工具：

```text
shared_literature_search
private_paper_search
paper_lookup
evidence_context_build
project_memory_lookup
workflow_agent
codex_plan
```

每个工具必须声明：

- 输入 schema
- 输出 schema
- 是否只读
- 是否需要人工审批
- 是否可以访问私有论文
- 超时和费用限制
- 审计记录方式

自然语言路由规则：

```text
“找相关论文”       → shared_literature_search
“查我的论文”       → private_paper_search
“总结这段内容”     → paper_lookup / context_build
“下一步做什么”     → workflow_agent
“帮我写分析代码”   → codex_plan
“直接运行代码”     → 必须进入人工审批和受控执行
```

## 5. Codex 到底是什么角色

当前代码里的 Codex 不是一个可以直接暴露给普通用户的“万能 Agent”。它是后端可选的代码生成提供者，由 `STEM_SCI_CODING_PROVIDER=codex` 控制。

它应该处在这里：

```text
DataAnalysisAgent 提出分析计划
→ Controller 生成代码规格
→ Codex 生成候选代码
→ 静态代码审查
→ 人工批准
→ 受控沙箱执行
→ 结果验证
```

当前项目应该把 Codex 当作受控的代码生成与分析辅助能力，而不是直接暴露给用户的任意命令执行终端。

因此当前阶段建议：

### 第一阶段

- Codex 只用于“生成候选分析代码”。
- 不允许用户输入任意 shell 命令。
- 不允许用户直接执行未经审查的代码。
- 不把 Codex API Key 放到前端。
- 前端只显示代码任务、审查状态、审批按钮和执行结果。

### 第二阶段

增加：

```text
POST /api/v1/projects/{project_id}/coding/tasks
GET  /api/v1/projects/{project_id}/coding/tasks
GET  /api/v1/projects/{project_id}/coding/tasks/{task_id}
POST /api/v1/projects/{project_id}/coding/tasks/{task_id}/approve
POST /api/v1/projects/{project_id}/coding/tasks/{task_id}/execute
```

`execute` 必须由后端执行，且绑定：

- 项目 ID
- 冻结数据哈希
- 代码哈希
- 代码审查结果
- 人工审批记录
- 沙箱限制

## 6. 六 Agent 和对话模型怎么协作

不要让六 Agent 直接取代 QA 对话模型。建议采用两层：

### 对话模型层

负责：

- 理解自然语言
- 判断用户意图
- 选择工具
- 组织回答
- 追问缺失信息

### 六 Agent Controller 层

负责：

- 选择具体研究角色
- 生成候选工件
- 执行确定性工具
- 记录审计
- 请求人工审批
- 推进或回退阶段

链路：

```text
用户自然语言
→ QA Router
→ tool call
→ retrieval / memory / workflow tool
→ Controller 或 KnowledgeService
→ 返回结构化结果
→ 对话模型组织成回答
```

关键边界：

```text
QA Router 可以建议 Agent
QA Router 不可以绕过 Controller 修改状态
Agent 可以产出候选
Agent 不可以批准、冻结、执行或发布
```

## 7. 长期记忆应该保存什么

### 7.1 应该保存

- 用户明确说出的研究方向
- 项目研究问题
- 已确认的研究范围
- 已批准的研究设计决定
- 用户明确要求长期保留的偏好
- 已核验的证据摘要和来源引用
- 未解决的问题
- 对话摘要和来源对话 ID
- Agent 运行和审批的引用

### 7.2 不应该直接保存

- 没有来源的模型猜测
- 未核验论文内容
- 完整原始数据行
- API Key、密码和私密配置
- 没有项目归属的跨用户内容
- 把一轮临时上下文当成永久事实

### 7.3 记忆读取策略

每次问答只取相关记忆：

```text
当前问题
→ 找相关项目记忆
→ 找相关论文 chunk
→ 找共享语料证据
→ 按 token budget 组装 ContextBundle
```

不要把整个历史对话无限拼接到 Prompt。

## 8. 前端重构安排

当前前端更像“研究驾驶舱”，下一步应改成“用户论文工作台”。

### 8.1 页面结构

```text
/login
/register
/projects
/projects/:project_id
/projects/:project_id/documents/:document_id
/projects/:project_id/workflow
/projects/:project_id/audit
```

### 8.2 登录后首页：我的研究项目

首页主要显示：

- 我的论文/研究项目列表
- 项目标题
- 研究方向
- 当前阶段
- 最近一次问答
- 最近更新时间
- 风险或待审批提示
- 新建项目按钮

不要在首页先展示大量 Agent 技术信息。

### 8.3 项目工作区

推荐布局：

```text
左侧：项目资料和论文目录
中间：主要对话窗口
右侧：回答引用、证据状态、Agent/审批状态
```

核心区域顺序：

```text
对话
→ 回答
→ 引用和原文
→ 检索状态
→ Agent 下一步建议
→ 工作流操作
```

### 8.4 论文编辑区

需要支持：

- Markdown 或富文本编辑
- 自动保存草稿
- 手动保存版本
- 查看版本差异
- 恢复旧版本
- 从回答引用插入参考文献
- 从论文选中文本发起提问

第一版建议先做 Markdown 编辑器，避免直接引入复杂的 Word 协同编辑。

### 8.5 Agent 面板

展示六个角色：

```text
研究导师
证据综述员
研究设计师
数据分析师
论文写作助手
独立审查员
```

每个 Agent 面板显示：

- 当前是否可调用
- 当前需要的输入
- 上一次运行结果
- 候选工件
- 风险
- 是否等待人工审批

### 8.6 Codex 面板

Codex 面板不应该看起来像开放终端，应显示：

- 分析计划
- 代码规格
- 代码候选
- 静态审查结果
- 数据哈希
- 执行审批
- 执行状态
- 结果验证

## 9. 推荐实施顺序

### Sprint 0：整理基线

目标：不改变已有检索和工作流行为。

- 固定当前分支和提交
- 清理未跟踪临时文件
- 保留当前 225 个后端测试通过状态
- 给现有 API 增加接口契约测试
- 将 SQLite Store 抽象成 Repository 接口

完成标准：

- 现有 QA、retrieval、workflow 测试全部通过
- 前端 `typecheck` 和 `build` 通过
- 能用一条命令启动前后端

### Sprint 1：用户、项目和权限

优先级最高。

- 用户注册、登录、退出
- 当前用户接口
- 项目 CRUD
- 项目成员隔离
- 现有接口接入身份检查

完成标准：

- 用户 A 看不到用户 B 的项目
- 未登录不能访问项目接口
- 前端登录后进入项目列表

### Sprint 2：论文和文档管理

- 文档上传
- 论文正文编辑
- 文档版本
- 原始文件和编辑稿分离
- 文档解析任务

完成标准：

- 用户可创建一篇论文
- 用户可上传参考 PDF
- 用户可直接修改论文草稿
- 关闭页面后内容不丢失

### Sprint 3：私有论文检索和长期记忆

- 项目私有 chunk
- 私有 BM25/FAISS 索引
- 共享语料 + 私有语料联合检索
- 对话持久化
- 项目记忆候选和确认

完成标准：

- 用户问“我的论文中……”时能检索自己的材料
- 返回结果带来源文件和 chunk
- 不会跨项目返回内容
- 多轮对话能延续上下文

### Sprint 4：工具路由和六 Agent 产品化

- LLM 工具注册表
- private search 工具
- memory lookup 工具
- workflow agent 工具
- Agent 面板
- 审批和 REWORK 前端

完成标准：

- 用户自然语言可以触发正确工具
- 工具调用有审计记录
- workflow_agent 只能提出建议
- Agent 不能绕过审批

### Sprint 5：Codex 受控使用

- 代码规格接口
- 候选代码生成
- 静态审查
- 人工批准
- 受控执行
- 结果验证

完成标准：

- 用户不能直接执行任意命令
- 每次运行绑定项目、数据和代码哈希
- Codex 失败或不可用时有明确状态
- 结果没有通过验证时不能进入论文正式结论

### Sprint 6：前端完整工作台

- 登录注册页
- 项目列表页
- 项目工作区
- 论文编辑器
- 对话和证据
- Agent 和 Codex 面板
- 审计页

完成标准：

- 新用户可以从注册进入创建论文
- 不看命令行也能完成 Demo 主流程
- 评委能看懂“问题、检索、证据、Agent、实验、审查”的关系

### Sprint 7：部署和比赛交付

- Docker Compose
- PostgreSQL
- Neo4j
- 后端
- 前端 Nginx
- HTTPS
- 域名
- 数据备份
- 演示账号
- 演示数据
- 监控和日志

## 10. 部署方案

### 10.1 推荐的比赛 Demo 方案

使用一台固定公网服务器：

```text
域名
→ HTTPS 反向代理
→ 前端静态页面
→ /api 代理到 FastAPI
→ PostgreSQL
→ Neo4j
→ 文件存储
→ 后端工作进程
```

前端只配置同一个域名下的 API：

```text
https://demo.example.com/api/v1
```

这样评委只需要打开一个地址，前端不需要暴露 `127.0.0.1:8000`，也不需要每次重启重新修改接口地址。

### 10.2 部署前必须完成

- 生产 `.env` 不提交 Git
- 修改 CORS 为正式域名
- 开启 HTTPS
- 增加登录认证
- 关闭 `STEM_SCI_ALLOW_UNVERIFIED_FORMAL_EVIDENCE`
- 配置 Neo4j 和论文资产
- 配置 PostgreSQL 备份
- 限制上传大小和文件类型
- 关闭详细异常返回
- 准备演示项目和演示账号

### 10.3 不建议的最终方案

- 直接把本地 `uvicorn` 暴露公网
- 依赖临时内网穿透作为比赛正式地址
- 把 API Key 写入前端
- 把 Neo4j 当用户权限主数据库
- 让公网用户直接调用 Codex shell
- 没有用户隔离就开放论文上传

## 11. 最终演示主线

建议比赛 Demo 固定为：

```text
注册/登录
→ 创建“生成式 AI 支架支持 Python 物理建模”研究项目
→ 上传一篇参考论文或打开已有演示资料
→ 在对话框提出研究问题
→ 返回共享论文 + 私有论文证据
→ 让证据综述 Agent 生成研究缺口和候选文献矩阵
→ 让研究设计 Agent 生成实验设计候选
→ 人工批准研究设计
→ 数据分析 Agent 生成分析计划
→ Codex 生成候选 Python 分析代码
→ 人工批准并执行
→ 展示验证结果和独立审查
```

评委最容易理解的不是“有多少接口”，而是：

```text
用户的问题如何变成证据
证据如何变成研究设计
研究设计如何变成可审计分析
分析结果如何回到论文
```

## 12. 当前最应该做的三件事

不要同时开发全部功能。推荐现在先做：

1. **先完成用户、项目和权限模型设计。**
2. **再完成论文文档 CRUD 和项目私有检索。**
3. **最后把现有 QA、六 Agent 和 Codex 接入项目工作区。**

原因是没有用户和项目边界，后面所有“我的论文”“我的记忆”“我的 Agent 审查”都无法安全实现。
