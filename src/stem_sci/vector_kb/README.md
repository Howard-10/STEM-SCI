# STEM Physics Education Knowledge Base

向量知识库，122 篇物理 STEM 教育论文，混合检索（语义 + 关键词）。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入千问 API Key

# 3. 检索
python query.py "你的问题"
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `vectordb/index.faiss` | FAISS 向量索引 (1077 条, 1024 维) |
| `vectordb/bm25.pkl` | BM25 关键词索引 |
| `vectordb/metadata.json` | 完整元数据 + 原文 |
| `query.py` | 混合检索脚本 |
| `requirements.txt` | Python 依赖 |

## 检索原理

向量语义搜索 + BM25 关键词搜索 → RRF 融合排序

## 论文覆盖

- AIMS STEM Education 期刊 (50 篇)
- IJSTEM 期刊 (34 篇)
- PRPER / IOP / 其他物理教育期刊 (38 篇)
- 总计 122 篇，涵盖 STEM/PBL、AI 教育、计算建模、教师发展、学习评价、研究方法
