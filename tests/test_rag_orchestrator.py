"""端到端测试 RAG Orchestrator."""

import os
import sys
from pathlib import Path

import pytest

if os.getenv("RUN_RAG_INTEGRATION") != "1":
    pytest.skip(
        "Set RUN_RAG_INTEGRATION=1 with LLM, DashScope, and Neo4j credentials to run",
        allow_module_level=True,
    )

# 确保项目路径（rag_orchestrator 已移至 STEM-SCI-repo/src/stem_sci/）
sys.path.insert(0, str(Path(__file__).resolve().parent / "STEM-SCI-repo" / "src" / "stem_sci"))

# 设置环境变量（优先使用外部环境变量，未设置时用默认值）
os.environ.setdefault("LLM_API_KEY", "sk-your-api-key-here")
os.environ.setdefault("LLM_BASE_URL", "https://api.deepseek.com")
os.environ.setdefault("LLM_MODEL", "deepseek-chat")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7688")
os.environ.setdefault("NEO4J_USERNAME", "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "12345678")

# 设置 stdout 为 utf-8 避免 GBK 编码错误
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stem_sci.rag_orchestrator.config import LLMConfig
from stem_sci.rag_orchestrator.pipeline import RAGPipeline

print("=" * 60)
print("  RAG Orchestrator -- End-to-End Test")
print("=" * 60)

# --- 1. LLM 连接测试 ---
print("\n[1] LLM connection test...")
config = LLMConfig.from_env()
try:
    client = config.create_client()
    resp = client.chat.completions.create(
        model=config.model,
        messages=[{"role": "user", "content": "Say 'OK' in one word."}],
        max_tokens=10,
    )
    print(f"  [PASS] LLM OK -- model={config.model}, response='{resp.choices[0].message.content.strip()}'")
except Exception as e:
    print(f"  [FAIL] LLM connection failed: {e}")
    sys.exit(1)

# --- 2. Pipeline 初始化 ---
print("\n[2] Pipeline init...")
try:
    pipeline = RAGPipeline(config=config, project_id="stem-sci")
    print(f"  [PASS] Pipeline ready -- {len(pipeline.registry.list_names())} tools: {pipeline.registry.list_names()}")
except Exception as e:
    print(f"  [FAIL] Pipeline init failed: {e}")
    sys.exit(1)

# --- 3. 路由测试 (规则) ---
print("\n[3] Route test (rule matching)...")
test_questions = [
    ("项目式学习对物理概念理解有什么效果？", "rule"),
    ("什么是建构主义学习理论？", "rule"),
    ("虚拟现实用什么教学法最有效？", "rule"),
    ("比较PBL和传统教学对编程能力的影响", "rule"),
    ("查一下 10.3934/steme.2026023 这篇论文", "rule"),
]
for q, expected_method in test_questions:
    decision = pipeline.route(q)
    status = "[PASS]" if decision.method == expected_method else "[WARN]"
    print(f"  {status} [{decision.method}] {decision.tool_name}: {q[:50]}...")

# --- 4. 向量检索测试 ---
print("\n[4] Vector search test...")
try:
    v_results = pipeline.registry.execute("vector_search", query="project-based learning physics", top_k=3)
    print(f"  [PASS] Vector search returned {len(v_results)} results")
    for r in v_results[:2]:
        if "error" in r:
            print(f"    [WARN] {r['error'][:100]}")
        else:
            print(f"    - [{r.get('paper_title','?')[:60]}] score={r.get('score',0)}")
except Exception as e:
    print(f"  [FAIL] Vector search failed: {e}")

# --- 5. 图谱查询测试 ---
print("\n[5] Graph query test...")
try:
    g_results = pipeline.registry.execute(
        "graph_query", keyword="project-based learning", limit=5
    )
    print(f"  [PASS] Graph query returned {len(g_results)} results")
    for r in g_results[:3]:
        if "error" in r:
            print(f"    [WARN] {r['error'][:100]}")
        else:
            print(f"    - {r.get('head','?')} --[{r.get('relation','?')}]--> {r.get('tail','?')}")
except Exception as e:
    print(f"  [FAIL] Graph query failed: {e}")

# --- 6. 完整 RAG 流程测试 ---
print("\n[6] Full RAG pipeline test...")
test_q = "项目式学习对物理概念理解有什么效果？"
print(f"  Question: {test_q}")
try:
    result = pipeline.answer(test_q)
    print(f"  [PASS] Route: {result.route_decision.tool_name} ({result.route_decision.method})")
    print(f"  [PASS] Citations: {len(result.citations)}")
    print(f"  [PASS] Time: {result.elapsed_ms:.0f}ms")
    print(f"  Answer (first 400 chars):")
    print(f"  {result.answer[:400]}...")
    if result.error:
        print(f"  [WARN] Error: {result.error}")
except Exception as e:
    print(f"  [FAIL] Pipeline failed: {e}")
    import traceback
    traceback.print_exc()

# --- 7. 第二个测试 ---
print("\n[7] Second question test...")
test_q2 = "虚拟现实技术在物理教育中有什么应用？"
print(f"  Question: {test_q2}")
try:
    result2 = pipeline.answer(test_q2)
    print(f"  [PASS] Route: {result2.route_decision.tool_name} ({result2.route_decision.method})")
    print(f"  [PASS] Citations: {len(result2.citations)}")
    print(f"  [PASS] Time: {result2.elapsed_ms:.0f}ms")
    print(f"  Answer (first 400 chars):")
    print(f"  {result2.answer[:400]}...")
except Exception as e:
    print(f"  [FAIL] Pipeline failed: {e}")

print("\n" + "=" * 60)
print("  Test Complete!")
print("=" * 60)
