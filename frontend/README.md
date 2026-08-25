# STEM-SCI frontend

This React/Vite workspace implements the STEM-SCI workflow workspace and its Context MVP integration. It supports project creation, six-Agent workflow state, approval and REWORK feedback, audit views, and project-scoped Markdown/TXT/JSON/text-extractable-PDF import with evidence search, source verification, SourceChunk trace-back, and ContextBundle inspection. Image-only or scanned PDFs need future OCR support.

Copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL` and `VITE_PROJECT_ID` as needed. The backend must receive `STEM_SCI_CORS_ORIGINS` containing the frontend origin; its safe local default is `http://localhost:5173,http://127.0.0.1:5173`, never `*`. Its upload limit defaults to 50 MB and is configured server-side through `STEM_SCI_MAX_UPLOAD_BYTES`. Run `npm.cmd install`, `npm.cmd run dev`, `npm.cmd run typecheck`, and `npm.cmd run build` on Windows.
