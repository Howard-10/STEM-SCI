"""文献分层切片器 —— PDF 解析 + 四级分层切片.

层级: 文档 → 章节 → 段落 → 句子
每层携带溯源定位信息 (section_title, para_index, sent_index, page_start, page_end).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
import pdfplumber


# ============================================================================
# 数据模型
# ============================================================================


@dataclass
class Chunk:
    """文本切片."""

    text: str
    chunk_id: str
    sha256: str = ""

    # 溯源定位
    paper_id: str = ""
    section_title: str = ""
    para_index: int = 0
    sent_range: str = ""  # "3-5"
    page_start: int = 0
    page_end: int = 0

    # 统计
    token_count: int = 0

    def __post_init__(self):
        if not self.sha256:
            self.sha256 = hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]
        if not self.token_count:
            self.token_count = _estimate_tokens(self.text)


@dataclass
class ParsedPaper:
    """解析后的论文结构."""

    paper_id: str
    title: str = ""
    full_text: str = ""
    sections: list[dict] = field(default_factory=list)  # [{title, text, para_start, para_end}]
    chunks: list[Chunk] = field(default_factory=list)
    parse_status: str = "ok"
    parse_error: str = ""
    pdf_sha256: str = ""


# ============================================================================
# 工具函数
# ============================================================================


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数 (英文: ~4 char/token, 中文: ~1.5 char/token)."""
    en_chars = len(re.findall(r"[a-zA-Z0-9\s]", text))
    zh_chars = len(text) - en_chars
    return int(en_chars / 4 + zh_chars / 1.5)


def _clean_text(text: str) -> str:
    """清洗文本: 合并空白、去页眉页脚噪声."""
    text = re.sub(r"\n\s*\d+\s*\n", "\n", text)  # 独立页码
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


# ============================================================================
# PDF 解析
# ============================================================================


def _compute_sha256(file_path: Path) -> str:
    """计算文件 SHA256."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk_data in iter(lambda: f.read(8192), b""):
            sha.update(chunk_data)
    return sha.hexdigest()


# 全局解析缓存 (pdf_sha256 → ParsedPaper)
# 注意: 此缓存仅在当前进程有效，进程重启后失效
_parse_cache: dict[str, ParsedPaper] = {}


def parse_pdf(
    pdf_path: str | Path,
    *,
    paper_id: str = "",
    max_pages: int = 0,
    use_cache: bool = True,
) -> ParsedPaper:
    """解析 PDF 文件，提取全文文本和章节结构.

    Args:
        pdf_path: PDF 文件路径
        paper_id: 论文标识 (DOI)
        max_pages: 最大解析页数 (0 = 全部)
        use_cache: 是否使用 PDF 解析缓存（按 SHA256 去重，仅当前进程有效）

    Returns:
        ParsedPaper 含全文文本和章节信息
    """
    path = Path(pdf_path)
    if not path.exists():
        return ParsedPaper(
            paper_id=paper_id or path.stem,
            parse_status="error",
            parse_error=f"File not found: {pdf_path}",
        )

    # SHA256 缓存
    pdf_sha = ""
    if use_cache:
        try:
            pdf_sha = _compute_sha256(path)
            if pdf_sha in _parse_cache:
                cached = _parse_cache[pdf_sha]
                cached.paper_id = paper_id or cached.paper_id
                return cached
        except (OSError, PermissionError):
            pdf_sha = ""

    try:
        full_text_parts: list[str] = []
        sections: list[dict] = []
        current_section = {"title": "Abstract", "text": "", "para_start": 0, "para_end": 0}
        para_counter = 0
        page_para_map: dict[int, int] = {}  # para_index → page_number (1-indexed)

        with pdfplumber.open(path) as pdf:
            pages_to_read = pdf.pages[:max_pages] if max_pages > 0 else pdf.pages

            for page_idx, page in enumerate(pages_to_read):
                page_num = page_idx + 1  # 1-indexed
                text = page.extract_text()
                if not text:
                    continue
                text = _clean_text(text)

                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue

                    section_match = re.match(
                        r"^(\d+[\.\s]+[A-Z][A-Za-z\s\-]+)$", line
                    )
                    kw_match = re.match(
                        r"^(Introduction|Abstract|Method|Result|Discussion|"
                        r"Conclusion|Reference|Acknowledgement|Appendix)",
                        line,
                        re.IGNORECASE,
                    )

                    if (section_match or kw_match) and len(line) < 80:
                        if current_section["text"].strip():
                            current_section["para_end"] = para_counter
                            sections.append(current_section)
                        current_section = {
                            "title": line.strip(),
                            "text": "",
                            "para_start": para_counter,
                            "para_end": 0,
                        }
                    else:
                        current_section["text"] += line + " "
                        if line.endswith((".", "?", "!")):
                            # 记录段落→页面映射
                            page_para_map[para_counter] = page_num
                            para_counter += 1

                full_text_parts.append(text)

        if current_section["text"].strip():
            current_section["para_end"] = para_counter
            sections.append(current_section)

        full_text = "\n\n".join(full_text_parts)

        parsed = ParsedPaper(
            paper_id=paper_id or path.stem,
            title=sections[0]["title"] if sections else "",
            full_text=full_text,
            sections=sections,
            parse_status="ok",
            pdf_sha256=pdf_sha,
        )

        if use_cache and pdf_sha:
            _parse_cache[pdf_sha] = parsed

        return parsed

    except Exception as e:
        return ParsedPaper(
            paper_id=paper_id or path.stem,
            parse_status="error",
            parse_error=str(e),
        )


# ============================================================================
# 切片策略
# ============================================================================


def chunk_by_paragraph(
    paper: ParsedPaper,
    *,
    target_chunk_tokens: int = 1500,
    overlap_paras: int = 2,
    min_chunk_tokens: int = 200,
) -> list[Chunk]:
    """按段落切片，保持目标 token 数，相邻块有重叠.

    策略:
    1. 积累段落直到超过 target_chunk_tokens
    2. 回退 overlap_paras 个段落作为下一块的起点
    3. 太短的块 (< min_chunk_tokens) 合并到前一个

    Args:
        paper: 解析后的论文
        target_chunk_tokens: 每个块的目标 token 数
        overlap_paras: 相邻块重叠段落数
        min_chunk_tokens: 最小块 token 数

    Returns:
        切片列表
    """
    # 将全文按段落拆分
    paragraphs = _split_paragraphs(paper.full_text)
    if not paragraphs:
        return []

    # 构建段落→页面映射 (通过重新解析 PDF 获取)
    page_para_map = _build_page_para_map(paper)

    chunks: list[Chunk] = []
    i = 0
    chunk_idx = 0

    while i < len(paragraphs):
        current_tokens = 0
        start = i
        end = i

        # 积累段落直到达到目标 token 数
        while end < len(paragraphs) and current_tokens < target_chunk_tokens:
            current_tokens += _estimate_tokens(paragraphs[end])
            end += 1

        if end >= len(paragraphs):
            end = len(paragraphs)

        # 找到此块对应的章节
        section_title = _find_section_for_para(paper, start)

        # 确定页码范围
        page_start = page_para_map.get(start, 0)
        page_end = page_para_map.get(end - 1, page_start) if end > start else page_start

        chunk_text = "\n\n".join(paragraphs[start:end])
        token_count = _estimate_tokens(chunk_text)

        # 短块合并到前一个
        if token_count < min_chunk_tokens and chunks:
            chunks[-1].text += "\n\n" + chunk_text
            chunks[-1].token_count = _estimate_tokens(chunks[-1].text)
            chunks[-1].sha256 = hashlib.sha256(
                chunks[-1].text.encode("utf-8")
            ).hexdigest()[:16]
            chunks[-1].page_end = max(chunks[-1].page_end, page_end)
        else:
            chunk = Chunk(
                text=chunk_text,
                chunk_id=f"{paper.paper_id}_chunk_{chunk_idx:04d}",
                paper_id=paper.paper_id,
                section_title=section_title,
                para_index=start,
                sent_range=f"{start}-{end - 1}",
                page_start=page_start,
                page_end=page_end,
                token_count=token_count,
            )
            chunks.append(chunk)
            chunk_idx += 1

        # 移到下一块起点 (含重叠)
        i = max(end - overlap_paras, start + 1)
        if i >= len(paragraphs):
            break

    return chunks


def _split_paragraphs(text: str) -> list[str]:
    """将文本拆分为段落."""
    # 双换行分隔段落
    raw = re.split(r"\n\s*\n", text)
    return [p.strip() for p in raw if p.strip() and len(p.strip()) > 30]


def _find_section_for_para(paper: ParsedPaper, para_index: int) -> str:
    """根据段落索引查找所属章节."""
    for section in paper.sections:
        if section["para_start"] <= para_index <= section["para_end"]:
            return section["title"]
    return ""


def _build_page_para_map(paper: ParsedPaper) -> dict[int, int]:
    """从解析后的论文构建段落→页面映射.

    基于 section 结构的粗略估算。
    """
    page_map: dict[int, int] = {}
    total_paras = sum(
        s["para_end"] - s["para_start"] + 1
        for s in paper.sections
        if s["para_end"] > s["para_start"]
    )
    if total_paras == 0:
        return page_map
    # 粗略映射：均匀分配 (假设每页约 5 个段落)
    pages_estimate = max(1, total_paras // 5)
    paras_per_page = max(1, total_paras // pages_estimate)
    for para_idx in range(total_paras):
        page_map[para_idx] = (para_idx // paras_per_page) + 1
    return page_map


# ============================================================================
# 便捷函数
# ============================================================================


def parse_and_chunk(
    pdf_path: str | Path,
    *,
    paper_id: str = "",
    target_chunk_tokens: int = 1500,
    max_pages: int = 0,
) -> ParsedPaper:
    """一步完成解析 + 切片.

    Args:
        pdf_path: PDF 路径
        paper_id: 论文 ID
        target_chunk_tokens: 目标 chunk 大小 (token)
        max_pages: 最大页数 (0=全部, 用于快速测试)

    Returns:
        ParsedPaper 含 chunks
    """
    paper = parse_pdf(pdf_path, paper_id=paper_id, max_pages=max_pages)
    if paper.parse_status == "ok":
        paper.chunks = chunk_by_paragraph(paper, target_chunk_tokens=target_chunk_tokens)
    return paper
