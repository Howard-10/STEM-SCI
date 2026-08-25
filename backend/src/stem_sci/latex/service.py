"""Safe, deterministic conversion from manuscript text to standard LaTeX."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import LatexCompileResult, LatexGenerateRequest, LatexGenerateResponse, LatexTemplate

_TEMPLATES = (
    LatexTemplate(
        template_id="generic-article",
        name="通用 STEM 论文（Article）",
        venue_type="generic",
        publisher="STEM-SCI",
        description="适合预投稿整理的通用 article 模板，不代表任何期刊的官方格式。",
        version="1.0.0",
        official_status="generic",
        document_class="article",
    ),
    LatexTemplate(
        template_id="ieee-conference",
        name="IEEE Conference（社区映射）",
        venue_type="conference",
        publisher="IEEE",
        description="使用 IEEEtran 文档类的会议稿结构。投稿前必须以目标会议官网模板为准。",
        version="1.0.0",
        source_url="https://www.ieee.org/conferences/publishing/templates.html",
        official_status="community",
        document_class="IEEEtran",
    ),
    LatexTemplate(
        template_id="springer-nature",
        name="Springer Nature（社区映射）",
        venue_type="journal",
        publisher="Springer Nature",
        description="使用 sn-jnl 文档类的期刊稿结构。不同期刊的官方要求可能不同。",
        version="1.0.0",
        source_url="https://www.springernature.com/gp/authors/campaigns/latex",
        official_status="community",
        document_class="sn-jnl",
    ),
)

_COMMANDS = ("\\input", "\\include", "\\write18", "\\immediate", "\\openout", "\\inputminted")
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_LINK = re.compile(r"\[([^]]+)\]\(([^)]+)\)")


def list_templates() -> list[LatexTemplate]:
    return list(_TEMPLATES)


def get_template(template_id: str) -> LatexTemplate:
    for template in _TEMPLATES:
        if template.template_id == template_id:
            return template
    raise ValueError(f"unknown LaTeX template: {template_id}")


def latex_escape(value: str) -> str:
    """Escape user-authored plain text without allowing command injection."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def _format_inline(value: str) -> str:
    escaped = latex_escape(value)
    escaped = _INLINE_CODE.sub(lambda match: r"\texttt{" + latex_escape(match.group(1)) + "}", escaped)
    return _LINK.sub(lambda match: latex_escape(match.group(1)), escaped)


def markdown_to_latex(content: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    in_list = False

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(_format_inline(" ".join(item.strip() for item in paragraph)))
            paragraph.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            blocks.append(r"\end{itemize}")
            in_list = False

    for raw_line in content.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            close_list()
            continue
        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            command = {1: "section", 2: "subsection", 3: "subsubsection"}[level]
            blocks.append(f"\\{command}{{{_format_inline(heading.group(2))}}}")
            continue
        if line.startswith("- ") or line.startswith("* "):
            flush_paragraph()
            if not in_list:
                blocks.append(r"\begin{itemize}")
                in_list = True
            blocks.append(f"\\item {_format_inline(line[2:])}")
            continue
        close_list()
        paragraph.append(line)
    flush_paragraph()
    close_list()
    return "\n\n".join(blocks)


def validate_latex(source: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not source.strip():
        errors.append("LaTeX source is empty")
    if "\\documentclass" not in source:
        errors.append("Missing \\documentclass")
    if "\\begin{document}" not in source or "\\end{document}" not in source:
        errors.append("Document body must contain \\begin{document} and \\end{document}")
    for command in _COMMANDS:
        if command in source:
            errors.append(f"Unsafe command is not allowed: {command}")
    for environment in ("document", "abstract", "itemize"):
        opened = len(re.findall(rf"\\begin\{{{environment}\}}", source))
        closed = len(re.findall(rf"\\end\{{{environment}\}}", source))
        if opened != closed:
            errors.append(f"Unbalanced {environment} environment")
    if "TODO" in source or "TBD" in source:
        warnings.append("Source contains TODO/TBD placeholders")
    if "\\bibliography{" not in source and "\\begin{thebibliography}" not in source:
        warnings.append("No bibliography block was generated")
    return errors, warnings


def _preamble(template: LatexTemplate) -> str:
    if template.document_class == "IEEEtran":
        return r"\documentclass[conference]{IEEEtran}" + "\n" + r"\usepackage{cite}"
    if template.document_class == "sn-jnl":
        return r"\documentclass[pdflatex,sn-mathphys-num]{sn-jnl}"
    return r"\documentclass[11pt,a4paper]{article}" + "\n" + r"\usepackage[a4paper,margin=1in]{geometry}"


def render_latex(request: LatexGenerateRequest, template: LatexTemplate) -> str:
    authors = " \\and ".join(latex_escape(author) for author in request.authors if author.strip())
    author_block = authors or "Author"
    keywords = ", ".join(latex_escape(keyword) for keyword in request.keywords if keyword.strip())
    body = markdown_to_latex(request.content)
    bibliography = request.bibliography.strip()
    bibliography_block = ""
    if bibliography:
        bibliography_block = "\n\n" + (bibliography if bibliography.startswith("\\") else r"\begin{thebibliography}{9}" + "\n" + bibliography + "\n" + r"\end{thebibliography}")
    keyword_block = f"\n\\textbf{{Keywords:}} {keywords}" if keywords else ""
    abstract_block = f"\\begin{{abstract}}\n{_format_inline(request.abstract)}\n\\end{{abstract}}\n" if request.abstract.strip() else ""
    return "\n".join(
        [
            "% Generated by STEM-SCI; verify against the target venue's current author guide.",
            _preamble(template),
            r"\usepackage[T1]{fontenc}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage{amsmath,amssymb,booktabs,graphicx,hyperref}",
            r"\title{" + latex_escape(request.title) + "}",
            r"\author{" + author_block + "}",
            r"\begin{document}",
            r"\maketitle",
            abstract_block.rstrip(),
            keyword_block,
            body,
            bibliography_block,
            r"\end{document}",
            "",
        ]
    )


def compile_pdf(source: str) -> LatexCompileResult:
    engine = next((candidate for candidate in ("latexmk", "pdflatex") if shutil.which(candidate)), None)
    if engine is None:
        return LatexCompileResult(status="skipped", log="No latexmk or pdflatex found; source validation completed.")
    with tempfile.TemporaryDirectory(prefix="stem-sci-latex-") as directory:
        root = Path(directory) / "manuscript"
        root.with_suffix(".tex").write_text(source, encoding="utf-8")
        command = [engine, "-interaction=nonstopmode", "-halt-on-error", root.name]
        if engine == "latexmk":
            command.insert(1, "-pdf")
        completed = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=60, check=False)
        log = (completed.stdout + "\n" + completed.stderr).strip()[-20_000:]
        pdf_available = root.with_suffix(".pdf").exists()
        errors = [line.strip() for line in log.splitlines() if line.startswith("!")]
        warnings = [line.strip() for line in log.splitlines() if "Warning" in line][-20:]
        return LatexCompileResult(
            status="compiled" if completed.returncode == 0 and pdf_available else "failed",
            engine=engine,
            pdf_available=pdf_available,
            log=log,
            errors=errors,
            warnings=warnings,
        )


class LatexService:
    def templates(self) -> list[LatexTemplate]:
        return list_templates()

    def generate(self, request: LatexGenerateRequest) -> LatexGenerateResponse:
        template = get_template(request.template_id)
        source = render_latex(request, template)
        errors, warnings = validate_latex(source)
        compilation = LatexCompileResult(status="skipped", log="Compilation was not requested.")
        if request.compile_pdf and not errors:
            compilation = compile_pdf(source)
        return LatexGenerateResponse(
            template=template,
            latex=source,
            sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            validation_errors=errors,
            validation_warnings=warnings,
            compile=compilation,
        )
# paragraph formatting marker
