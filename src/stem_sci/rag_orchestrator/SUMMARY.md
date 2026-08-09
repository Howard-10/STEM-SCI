# RAG Orchestrator — 完成总结

## 做了什么

构建了 `rag_orchestrator/` 模块，将大语言模型 + 图数据库(Neo4j) + 向量库(FAISS+BM25) 串联为一个统一的检索编排层。

### 模块结构

```
rag_orchestrator/
├── __init__.py          # 包入口，导出 RAGPipeline
├── config.py            # LLM 配置（OpenAI 兼容，一行换接口）
├── tool_registry.py     # 工具注册表（4 个检索工具 + 可扩展 Agent 工具）
├── retriever.py         # 统一检索层（封装 vector_kb + graph_store）
├── router.py            # LLM 路由（规则匹配 + function-calling 双通道）
├── synthesizer.py       # 答案合成（带溯源引用）
└── pipeline.py          # 主编排器（串联路由→检索→合成）
```

### 核心流程

```
用户问题(已改写)
    │
    ▼
Router (规则优先 → LLM function-calling 兜底)
    │
    ├── vector_search   → FAISS+BM25 全文检索
    ├── graph_query     → Neo4j 图谱关系查询
    ├── paper_lookup    → 论文精确查找
    └── hybrid_search   → 向量+图谱并行
    │
    ▼
Synthesizer (LLM 答案合成)
    │
    ▼
RAGResponse {answer, citations, route_decision}
```

## 测试结果

| 模块 | 状态 | 备注 |
|------|------|------|
| LLM 连接 (DeepSeek) | ✅ | `deepseek-chat` 正常 |
| 路由 — 规则匹配 | ✅ | 5/7 题命中规则，2/7 走 LLM |
| 路由 — LLM function-calling | ✅ | 正确选择工具 |
| 图谱查询 | ✅ | 返回 7 条三元组 (project-based learning) |
| 答案合成 | ✅ | 带 [来源G1]...[来源G9] 溯源引用 |
| 向量检索 | ⚠️ | 需 DashScope API key |

### 实测案例

**Q: 虚拟现实技术在物理教育中有什么应用？**

> Route: hybrid_search → 图谱返回 9 条关系 → 合成答案：
> - VR 作为混合现实实验室环境 (NOMR)，探索性学习，提升投入度 [来源G1-G7]
> - CAVE 沉浸式 VR 提升职前教师密度概念理解 [来源G9]

**Q: 项目式学习对物理概念理解有什么效果？**

> Route: vector_search → 向量库需 API key → 明确回复「当前检索结果不足以回答」而非编造

## 换 LLM 接口

只需改 2-3 行：

```python
# DeepSeek (当前)
config = LLMConfig.deepseek(api_key="sk-xxx")

# 换成 OpenAI → 改 1 行
config = LLMConfig.openai(api_key="sk-xxx")

# 换成本地 vLLM → 改 1 行
config = LLMConfig.local(port=8000, model="qwen2.5-7b")

# 传给 Pipeline
pipeline = RAGPipeline(config=config)
```

或设置环境变量（无需改代码）：

```bash
export LLM_API_KEY=sk-xxx
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o
```

## 如何继续

### 1. 让向量检索可用

向队友要 DashScope API key，创建 `.env` 文件：

```bash
cd vector_kb\(1\)/vector_kb/
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY=sk-xxx
```

### 2. 对接 6 个 Agent

在 `pipeline.py` 中注册 Agent 工具：

```python
# 示例：注册队友的「证据综述 Agent」
pipeline.registry.register(ToolSpec(
    name="evidence_synthesis",
    description="系统性综述文献证据，生成证据矩阵和冲突分析",
    parameters={...},  # JSON Schema
    handler=evidence_agent.run,  # 队友的 Python 函数
    category="agent",
))
```

注册后，LLM Router 自动学会调用这个 Agent。

### 3. 接入提示词改写

队友的提示词改写模块作为前置步骤：

```python
# 队友模块
rewritten_q = prompt_rewriter.rewrite(user_raw_question)

# 你模块
result = pipeline.answer(rewritten_q)
```

### 4. Memory 模块

规划文件：`src/memory/` → `short_memory.py` + `long_memory.py` + `memory_manager.py`

```
[对话历史] → Memory Manager → Router → Retriever → Synthesizer
                                   ↑___________________|
                                   (检索结果写入 memory)
```

### 5. 启动 Docker 后的完整测试命令

```bash
# 1. 启动 Neo4j
docker start neo4j-paper-graph

# 2. 设置环境变量
export LLM_API_KEY=YOUR_DEEPSEEK_API_KEY
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-chat
export NEO4J_URI=bolt://localhost:7688
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=12345678

# 3. 运行测试
cd "C:\Users\25946\Desktop\揭榜挂帅比赛"
python test_rag_orchestrator.py
```

## 文件清单

| 文件 | 路径 |
|------|------|
| 主编排器 | `rag_orchestrator/pipeline.py` |
| LLM 配置 | `rag_orchestrator/config.py` |
| 工具注册 | `rag_orchestrator/tool_registry.py` |
| 统一检索 | `rag_orchestrator/retriever.py` |
| 路由模块 | `rag_orchestrator/router.py` |
| 答案合成 | `rag_orchestrator/synthesizer.py` |
| 测试脚本 | `test_rag_orchestrator.py` |
| 本总结   | `rag_orchestrator/SUMMARY.md` |
