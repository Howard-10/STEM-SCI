# LaTeX submission formatting

The formatter is available through two endpoints:

- `GET /api/v1/latex/templates` lists versioned templates and their status.
- `POST /api/v1/latex/generate` accepts manuscript metadata and Markdown, returns standard `.tex` source, SHA-256, validation messages, and optional local compilation status.

## Safety and scope

The initial catalog includes a generic article template, an IEEEtran community mapping, and a Springer Nature community mapping. The latter two are not claimed to be the official template for every venue; users must verify the current author guide before submission.

The service escapes user-authored text, rejects shell/file-writing LaTeX commands, checks document/environment balance, and never executes compilation unless `compile_pdf=true` is explicitly requested. If `latexmk` or `pdflatex` is unavailable, generation still returns valid source with `compile.status=skipped`.

## Local verification

From the repository root:

```powershell
python -m pip install -e "./backend[dev]"
python -m pytest backend/tests/test_latex_service.py
python -m compileall -q backend/src/stem_sci/latex
cd frontend
npm install
npm run build
```

Install a TeX distribution separately when PDF compilation is required. A minimal production deployment should mount the generated artifacts to object storage and pin the exact venue template revision after editorial approval.
