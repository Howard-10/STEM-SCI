from stem_sci.latex.models import LatexGenerateRequest
from stem_sci.latex.service import LatexService, markdown_to_latex, validate_latex


def test_markdown_conversion_escapes_text_and_preserves_headings() -> None:
    result = markdown_to_latex("# Intro\n\nA & B_1\n\n- first\n- second")
    assert r"\section{Intro}" in result
    assert r"A \& B\_1" in result
    assert r"\begin{itemize}" in result
    assert r"\item second" in result


def test_generation_returns_stable_validated_source() -> None:
    response = LatexService().generate(
        LatexGenerateRequest(
            template_id="generic-article",
            title="Safe title",
            authors=["A & B"],
            abstract="A short abstract.",
            content="# Results\n\nThe result is 1% better.",
            keywords=["STEM"],
            compile_pdf=False,
        )
    )
    assert response.validation_errors == []
    assert response.compile.status == "skipped"
    assert response.sha256
    assert r"\documentclass[11pt,a4paper]{article}" in response.latex
    assert r"A \& B" in response.latex


def test_unsafe_commands_are_rejected() -> None:
    errors, _ = validate_latex(
        r"\documentclass{article}\begin{document}\write18{touch /tmp/x}\end{document}"
    )
    assert any("write18" in error for error in errors)


def test_unknown_template_is_rejected() -> None:
    try:
        LatexService().generate(LatexGenerateRequest(template_id="not-a-template"))
    except ValueError as error:
        assert "unknown LaTeX template" in str(error)
    else:
        raise AssertionError("unknown templates must fail closed")
