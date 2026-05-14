# `scripts/reports/`

One-off generators for documentation, demo assets, and codebase snapshots. Outputs land in `outputs/` (gitignored).

| Script | Purpose | Run as |
| --- | --- | --- |
| `generate_demo_assets.py` | Regenerate the fictitious SAT sample PDF and the demo guide PDF from `docs/DEMO_GUIDE.md`. | `python3 scripts/reports/generate_demo_assets.py` |
| `extract_sources.py` | Walk the repo and emit a JSON snapshot of source files (used to feed AI context dumps). Accepts `--include / --exclude` glob patterns. | `python3 scripts/reports/extract_sources.py` |
| `build_report.py` | Build the architecture PDF (`CheckWise_Reporte_Profesional_Arquitectura_V1.pdf`) from the source-extract JSON. | `python3 scripts/reports/build_report.py` |

All three are optional. The product runs without them.
