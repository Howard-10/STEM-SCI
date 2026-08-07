"""Demo: 用模拟 LLM 跑 sparse profile 和 batch 两种模式，输出三元组结果。"""
import json
import os
import re
import sys
import time
from unittest.mock import MagicMock, patch

# Ensure the parent directory is in path so "import graph_rag" works
_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from graph_rag.entity_extract import EntityExtractor

# ── 模拟论文数据 ──
DEMO_PAPERS = [
    {
        "paper_id": "10.1000/STEM001",
        "title": "Effects of ChatGPT-Integrated Project-Based Learning on "
                 "Undergraduate Students' Conceptual Understanding of Thermodynamics",
        "abstract": (
            "This study employed a quasi-experimental design with 172 undergraduate "
            "physics students to investigate the effect of project-based learning "
            "integrated with ChatGPT on conceptual understanding of thermodynamics. "
            "The experimental group (n=86) used ChatGPT as a scaffolding tool during "
            "PBL activities, while the control group (n=86) received traditional "
            "lecture-based instruction. Results showed the experimental group "
            "significantly outperformed the control group on the Thermodynamics "
            "Conceptual Understanding Test (d=0.82, p<0.01). Students reported "
            "increased engagement and self-efficacy. The study concludes that "
            "AI-integrated PBL can effectively improve physics learning outcomes."
        ),
        "keywords": "ChatGPT; project-based learning; thermodynamics; quasi-experiment; "
                     "conceptual understanding",
    },
    {
        "paper_id": "10.1000/STEM002",
        "title": "A Systematic Review of Virtual Reality Applications in Physics Education",
        "abstract": (
            "Following PRISMA guidelines, we conducted a systematic review of 44 "
            "empirical studies on VR applications in physics education published "
            "between 2018-2024. Results show that VR is most frequently applied in "
            "mechanics (38%) and electromagnetism (27%). The most common pedagogical "
            "approaches integrated with VR are inquiry-based learning and game-based "
            "learning. Meta-analysis revealed a moderate overall effect on conceptual "
            "understanding (Hedges' g=0.65). VR was particularly effective for "
            "visualizing abstract phenomena such as electric fields and wave propagation."
        ),
        "keywords": "virtual reality; physics education; systematic review; PRISMA; "
                     "conceptual understanding",
    },
    {
        "paper_id": "10.1000/STEM003",
        "title": "The Impact of Generative AI Feedback on Pre-service Teachers' "
                 "Scientific Modelling Competence",
        "abstract": (
            "This mixed-methods study examined how generative AI feedback affects "
            "pre-service science teachers' modelling competence. 64 pre-service "
            "teachers participated in a 12-week intervention where they used an "
            "AI-powered modelling platform that provided real-time feedback on "
            "their scientific models. Pre-post tests showed significant improvement "
            "in modelling competence (d=0.94). Qualitative analysis revealed that "
            "AI feedback helped students identify misconceptions and refine model "
            "structures. The study suggests AI scaffolding can serve as an effective "
            "cognitive tool in science teacher education."
        ),
        "keywords": "generative AI; pre-service teachers; scientific modelling; "
                     "feedback; teacher education",
    },
]

MOCK_PROFILE_RESPONSES = {
    "10.1000/STEM001": "{\"triples\": [{\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"USES_METHOD\", \"tail\": \"quasi-experimental design\", \"tail_type\": \"ResearchMethod\", \"evidence\": \"This study employed a quasi-experimental design with 172 undergraduate physics students\", \"confidence\": 1.0, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"ADOPTS_PEDAGOGY\", \"tail\": \"project-based learning\", \"tail_type\": \"PedagogicalMethod\", \"evidence\": \"effect of project-based learning integrated with ChatGPT\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"DEPLOYS_TECH\", \"tail\": \"ChatGPT\", \"tail_type\": \"Technology\", \"evidence\": \"project-based learning integrated with ChatGPT\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"STUDIES_DOMAIN\", \"tail\": \"thermodynamics\", \"tail_type\": \"SubjectDomain\", \"evidence\": \"conceptual understanding of thermodynamics\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"TARGETS_OUTCOME\", \"tail\": \"conceptual understanding\", \"tail_type\": \"LearningOutcome\", \"evidence\": \"significantly outperformed the control group on the Thermodynamics Conceptual Understanding Test\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"TARGETS_OUTCOME\", \"tail\": \"student engagement\", \"tail_type\": \"LearningOutcome\", \"evidence\": \"Students reported increased engagement\", \"confidence\": 0.9, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"TARGETS_OUTCOME\", \"tail\": \"self-efficacy\", \"tail_type\": \"LearningOutcome\", \"evidence\": \"increased engagement and self-efficacy\", \"confidence\": 0.9, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"INVOLVES_POPULATION\", \"tail\": \"undergraduate students\", \"tail_type\": \"StudentPopulation\", \"evidence\": \"172 undergraduate physics students\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"HAS_SAMPLE\", \"tail\": \"N=172, experimental n=86, control n=86\", \"tail_type\": \"SampleInfo\", \"evidence\": \"172 undergraduate physics students ... experimental group (n=86) [...] control group (n=86)\", \"confidence\": 1.0, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"HAS_EFFECT_SIZE\", \"tail\": \"d=0.82\", \"tail_type\": \"EffectSize\", \"evidence\": \"d=0.82, p<0.01\", \"confidence\": 1.0, \"layer\": \"L3\"}, {\"head\": \"10.1000/STEM001\", \"head_type\": \"Paper\", \"relation\": \"CLAIMS\", \"tail\": \"enhanced thermodynamics conceptual understanding via AI-integrated PBL\", \"tail_type\": \"Claim\", \"evidence\": \"AI-integrated PBL can effectively improve physics learning outcomes\", \"confidence\": 0.9, \"layer\": \"L2\"}]}",
    "10.1000/STEM002": "{\"triples\": [{\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"USES_METHOD\", \"tail\": \"systematic review\", \"tail_type\": \"ResearchMethod\", \"evidence\": \"Following PRISMA guidelines, we conducted a systematic review of 44 empirical studies\", \"confidence\": 1.0, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"USES_METHOD\", \"tail\": \"PRISMA\", \"tail_type\": \"ReportingGuideline\", \"evidence\": \"Following PRISMA guidelines\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"DEPLOYS_TECH\", \"tail\": \"virtual reality\", \"tail_type\": \"Technology\", \"evidence\": \"systematic review of 44 empirical studies on VR applications in physics education\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"STUDIES_DOMAIN\", \"tail\": \"mechanics\", \"tail_type\": \"SubjectDomain\", \"evidence\": \"VR is most frequently applied in mechanics (38%)\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"STUDIES_DOMAIN\", \"tail\": \"electromagnetism\", \"tail_type\": \"SubjectDomain\", \"evidence\": \"mechanics (38%) and electromagnetism (27%)\", \"confidence\": 0.9, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"ADOPTS_PEDAGOGY\", \"tail\": \"inquiry-based learning\", \"tail_type\": \"PedagogicalMethod\", \"evidence\": \"most common pedagogical approaches integrated with VR are inquiry-based learning and game-based learning\", \"confidence\": 0.9, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"ADOPTS_PEDAGOGY\", \"tail\": \"game-based learning\", \"tail_type\": \"PedagogicalMethod\", \"evidence\": \"inquiry-based learning and game-based learning\", \"confidence\": 0.9, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"TARGETS_OUTCOME\", \"tail\": \"conceptual understanding\", \"tail_type\": \"LearningOutcome\", \"evidence\": \"moderate overall effect on conceptual understanding\", \"confidence\": 0.9, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"HAS_EFFECT_SIZE\", \"tail\": \"Hedges g=0.65\", \"tail_type\": \"EffectSize\", \"evidence\": \"Hedges g=0.65\", \"confidence\": 1.0, \"layer\": \"L3\"}, {\"head\": \"10.1000/STEM002\", \"head_type\": \"Paper\", \"relation\": \"CLAIMS\", \"tail\": \"effectiveness of VR for visualizing abstract physics phenomena\", \"tail_type\": \"Claim\", \"evidence\": \"VR was particularly effective for visualizing abstract phenomena such as electric fields and wave propagation\", \"confidence\": 0.9, \"layer\": \"L3\"}]}",
    "10.1000/STEM003": "{\"triples\": [{\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"USES_METHOD\", \"tail\": \"mixed-methods\", \"tail_type\": \"ResearchMethod\", \"evidence\": \"This mixed-methods study examined\", \"confidence\": 1.0, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"DEPLOYS_TECH\", \"tail\": \"generative AI\", \"tail_type\": \"Technology\", \"evidence\": \"generative AI feedback affects pre-service science teachers modelling competence\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"ADOPTS_PEDAGOGY\", \"tail\": \"AI-powered scaffolding\", \"tail_type\": \"PedagogicalMethod\", \"evidence\": \"AI scaffolding can serve as an effective cognitive tool\", \"confidence\": 0.85, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"INVOLVES_POPULATION\", \"tail\": \"pre-service science teachers\", \"tail_type\": \"StudentPopulation\", \"evidence\": \"64 pre-service science teachers participated\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"TARGETS_OUTCOME\", \"tail\": \"scientific modelling competence\", \"tail_type\": \"LearningOutcome\", \"evidence\": \"significant improvement in modelling competence\", \"confidence\": 0.95, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"HAS_SAMPLE\", \"tail\": \"N=64, 12-week intervention\", \"tail_type\": \"SampleInfo\", \"evidence\": \"64 pre-service teachers participated in a 12-week intervention\", \"confidence\": 1.0, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"HAS_EFFECT_SIZE\", \"tail\": \"d=0.94\", \"tail_type\": \"EffectSize\", \"evidence\": \"Pre-post tests showed significant improvement in modelling competence (d=0.94)\", \"confidence\": 1.0, \"layer\": \"L3\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"CLAIMS\", \"tail\": \"enhanced modelling competence via generative AI feedback\", \"tail_type\": \"Claim\", \"evidence\": \"AI feedback helped students identify misconceptions and refine model structures\", \"confidence\": 0.9, \"layer\": \"L3\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"TARGETS_OUTCOME\", \"tail\": \"misconception identification\", \"tail_type\": \"LearningOutcome\", \"evidence\": \"AI feedback helped students identify misconceptions\", \"confidence\": 0.85, \"layer\": \"L2\"}, {\"head\": \"10.1000/STEM003\", \"head_type\": \"Paper\", \"relation\": \"EMPLOYS_ASSESSMENT\", \"tail\": \"pre-post test\", \"tail_type\": \"Assessment\", \"evidence\": \"Pre-post tests showed significant improvement\", \"confidence\": 0.9, \"layer\": \"L2\"}]}"
}


def run_demo():
    with patch("graph_rag.entity_extract.OpenAI") as mock_ai:
        client = MagicMock()
        mock_ai.return_value = client

        def api_side_effect(**kwargs):
            """根据 prompt 中的 paper_id 返回对应 mock 响应."""
            messages = kwargs.get("messages", [])
            user_content = ""
            for m in messages:
                if m.get("role") == "user":
                    user_content = m.get("content", "")
                    break
            # 从 user prompt 中提取 paper_id
            match = re.search(r'paper_id:\s*(\S+)', user_content)
            pid = match.group(1) if match else "unknown"

            resp_json = MOCK_PROFILE_RESPONSES.get(pid, '{"triples": []}')
            time.sleep(0.02)  # 模拟延迟

            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = resp_json
            mock_resp.usage = MagicMock(
                total_tokens=len(resp_json) // 2,
                prompt_tokens=len(user_content) // 3,
                completion_tokens=len(resp_json) // 5,
            )
            return mock_resp

        client.chat.completions.create.side_effect = api_side_effect

        extractor = EntityExtractor(
            api_base="http://localhost/v1",
            api_key="sk-demo",
            model_id="demo-model",
            max_tokens=2048,
            temperature=0.1,
            max_retries=1,
            retry_delay=0.5,
            cache_dir="",
        )

        print("=" * 75)
        print("  GraphRAG 稀疏论文画像抽取 Demo")
        print("  模式: PROFILE (仅标题+摘要+关键词)")
        print(f"  论文数: {len(DEMO_PAPERS)}")
        print("=" * 75)

        all_triples = []
        for i, paper in enumerate(DEMO_PAPERS, 1):
            print(f"\n{'─' * 65}")
            print(f"  论文 {i}: {paper['paper_id']}")
            print(f"  标题: {paper['title'][:70]}...")
            print(f"{'─' * 65}")

            result = extractor.extract_sparse_profile(
                paper_id=paper["paper_id"],
                title=paper["title"],
                abstract=paper["abstract"],
                keywords=paper["keywords"],
                max_triples=30,
                use_cache=False,
            )

            print(f"  模式: {result.mode}")
            print(f"  三元组数: {result.total_triples}")
            print(f"  丢弃数: {result.discarded_triples}")
            print(f"  缓存命中: {result.cache_hits}")
            print(f"  重试次数: {result.retry_count}")
            print()

            for cr in result.chunks:
                for t in cr.triples:
                    print(f"  [{t.relation}] ({t.head_type}) {t.head} "
                          f"→ ({t.tail_type}) {t.tail}")
                    print(f"    evidence: \"{t.evidence}\"")
                    print(f"    confidence={t.confidence}  layer={t.layer}")
                    if t.new_type_suggestion:
                        print(f"    new_type_suggestion: {t.new_type_suggestion}")
                    all_triples.append(t)

        print(f"\n{'=' * 75}")
        print(f"  总览")
        print(f"{'=' * 75}")
        print(f"  论文总数:         {len(DEMO_PAPERS)}")
        print(f"  三元组总数:       {len(all_triples)}")
        print(f"  平均每篇:         {len(all_triples) / len(DEMO_PAPERS):.1f}")

        # 按关系类型统计
        from collections import Counter
        rel_counts = Counter(t.relation for t in all_triples)
        print(f"\n  关系类型分布:")
        for rel, cnt in rel_counts.most_common():
            pct = cnt / len(all_triples) * 100
            print(f"    {rel:25s} {cnt:3d} ({pct:5.1f}%)")

        # 按实体类型统计
        head_types = Counter(t.head_type for t in all_triples)
        tail_types = Counter(t.tail_type for t in all_triples)
        print(f"\n  head_type 分布:")
        for ht, cnt in head_types.most_common():
            print(f"    {ht:25s} {cnt:3d}")
        print(f"\n  tail_type 分布:")
        for tt, cnt in tail_types.most_common():
            print(f"    {tt:25s} {cnt:3d}")

        # 统计信息
        stats = extractor.get_stats()
        print(f"\n  抽取统计:")
        print(f"    API 请求次数:    {stats.api_requests}")
        print(f"    缓存命中:        {stats.cache_hits}")
        print(f"    缓存未命中:      {stats.cache_misses}")
        print(f"    重试次数:        {stats.retries}")
        print(f"    总 tokens:       {stats.total_tokens}")
        print(f"    耗时:            {stats.elapsed_seconds:.2f}s")
        print(f"    预估费用:        CNY {stats.cost_yuan:.4f}")

        # 检查质量
        paper_relations = sum(1 for t in all_triples if t.head_type == "Paper")
        related_to = sum(1 for t in all_triples if t.relation == "RELATED_TO")
        self_loops = sum(1 for t in all_triples if t.head == t.tail)
        print(f"\n  质量检查:")
        print(f"    Paper→Entity 关系: {paper_relations}/{len(all_triples)} ({'OK' if paper_relations > 0 else 'X'})")
        print(f"    RELATED_TO 数量:   {related_to} ({'OK ≤2/篇' if related_to <= 2*len(DEMO_PAPERS) else 'X 过多'})")
        print(f"    自循环数:          {self_loops} ({'OK' if self_loops == 0 else 'X'})")

        # 输出 JSON 格式（供 Neo4j 导入）
        output_path = os.path.join(os.path.dirname(__file__), "demo_output.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "papers": len(DEMO_PAPERS),
                    "total_triples": len(all_triples),
                    "triples": [
                        {
                            "head": t.head, "head_type": t.head_type,
                            "relation": t.relation,
                            "tail": t.tail, "tail_type": t.tail_type,
                            "evidence": t.evidence, "confidence": t.confidence,
                            "layer": t.layer, "source_chunk_id": t.source_chunk_id,
                        }
                        for t in all_triples
                    ],
                },
                f, ensure_ascii=False, indent=2,
            )
        print(f"\n  完整结果已保存到: {output_path}")
        print("=" * 75)


if __name__ == "__main__":
    run_demo()
