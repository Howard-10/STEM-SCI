# RAG Orchestrator

大语言模型 + 图数据库(Neo4j) + 向量库(FAISS+BM25) 统一检索编排层。

## 概述

RAG Orchestrator 是 STEM-SCI 项目的核心检索模块，负责：

- **智能路由**：规则匹配 + LLM function-calling 双通道，自动决定查询哪个数据源
- **多源检索**：向量库全文搜索、Neo4j 知识图谱查询、论文精确查找、混合并行检索
- **答案合成**：基于检索证据生成带溯源的答案，标注 `[来源V1]`/`[来源G1]` 引用

```
用户问题
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

## 文件结构

```
rag_orchestrator/
├── __init__.py          # 包入口，导出 RAGPipeline
├── config.py            # LLM 配置（OpenAI 兼容，一行换接口）
├── tool_registry.py     # 工具注册表（4 个检索工具 + 可扩展 Agent 工具）
├── retriever.py         # 统一检索层（封装 vector_kb + graph_store）
├── router.py            # LLM 路由（规则匹配 + function-calling 双通道）
├── synthesizer.py       # 答案合成（带溯源引用）
├── pipeline.py          # 主编排器（串联路由→检索→合成）
├── SUMMARY.md           # 开发总结与架构说明
└── README.md            # 本文件
```

## 环境要求

### 依赖安装

```bash
pip install openai neo4j faiss-cpu dashscope scikit-learn
```

### Docker（Neo4j）

```bash
docker start neo4j-paper-graph
```

Neo4j 默认连接：`bolt://localhost:7688`（用户名 `neo4j`，密码 `12345678`）

### 向量库

确保 `vector_kb(1)/vector_kb/vectordb/` 目录存在且包含 FAISS 索引文件。

向量库使用阿里云 DashScope `text-embedding-v3` 做嵌入，需要单独配置 API key：
```bash
cd vector_kb(1)/vector_kb/
export DASHSCOPE_API_KEY=your-dashscope-key
```

## 快速开始

### 1. 设置环境变量

```bash
# LLM 配置（DeepSeek 示例）
export LLM_API_KEY=YOUR_DEEPSEEK_API_KEY
export LLM_BASE_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-chat

# Neo4j 配置
export NEO4J_URI=bolt://localhost:7688
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=12345678
```

### 2. Python API

```python
from rag_orchestrator.config import LLMConfig
from rag_orchestrator.pipeline import RAGPipeline

# 方式一：从环境变量自动读取
config = LLMConfig.from_env()
pipeline = RAGPipeline(config=config, project_id="stem-sci")

# 方式二：显式指定
config = LLMConfig(
    api_key="YOUR_DEEPSEEK_API_KEY",
    base_url="https://api.deepseek.com",
    model="deepseek-chat",
)
pipeline = RAGPipeline(config=config)

# 端到端问答
result = pipeline.answer("项目式学习对物理概念理解有什么效果？")
print(result.answer)           # markdown 格式答案
for c in result.citations:     # 引用来源
    print(f"[{c.source_type}] {c.paper_title}")

# 分步调用
decision = pipeline.route(question)       # Step 1: 路由
data = pipeline.retrieve(decision)        # Step 2: 检索
synth = pipeline.synthesize(question, data)  # Step 3: 合成

# 批量问答
results = pipeline.answer_batch([
    "项目式学习有什么效果？",
    "虚拟现实在物理教育中的应用？",
])

# JSON 输出
print(result.to_json())
```

## 切换 LLM 提供商

设计为 OpenAI 兼容接口，**改 1-2 行代码**即可切换：

```python
# DeepSeek（当前默认）
config = LLMConfig.deepseek(api_key="YOUR_DEEPSEEK_KEY")

# 切换到 OpenAI GPT-4o → 只改这 1 行
config = LLMConfig.openai(api_key="YOUR_OPENAI_KEY")

# 切换到本地 vLLM / Ollama → 只改这 1 行
config = LLMConfig.local(port=8000, model="qwen2.5-7b")

# 传给 Pipeline（之后无需任何改动）
pipeline = RAGPipeline(config=config)
```

或通过环境变量切换（代码零改动）：
```bash
export LLM_API_KEY=YOUR_OPENAI_KEY
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o
```

## 注册 Agent 工具

后续可将队友开发的 6 个 Agent 注册为工具，LLM Router 会自动学会调用：

```python
from rag_orchestrator.tool_registry import ToolSpec

pipeline.registry.register(ToolSpec(
    name="evidence_synthesis",
    description="系统性综述文献证据，生成证据矩阵和冲突分析",
    parameters={
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "检索关键词"},
            "paper_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["keyword"],
    },
    handler=evidence_agent.run,  # 队友的 Python 函数
    category="agent",
))
```

## 运行测试

```bash
# 确保 Docker Neo4j 已启动
docker start neo4j-paper-graph

# 运行测试
cd STEM-SCI-repo
python tests/test_rag_orchestrator.py
```

## Paper ID 格式说明

系统自动处理 4 种论文标识符格式：

| 格式 | 示例 |
|------|------|
| paper_id | `01_AIMS_10.3934_steme.2026023` |
| 文件名 | `01_AIMS_10.3934_steme.2026023.pdf` |
| DOI（斜杠） | `10.3934/steme.2026023` |
| DOI（点） | `10.3934.steme.2026023` |

所有格式通过 `normalize_paper_id()` 统一为 `{paper_id, doi}` 字典。
