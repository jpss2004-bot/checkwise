"""Build the _reference/sample-docs/ sandbox from a Banco Docs Sample ZIP.

Usage:
    python3 scripts/reports/build_sample_sandbox.py <path-to-zip> [--dst PATH]

Extracts the ZIP into a temp dir, normalizes filenames (lowercase slugs,
no diacritics), and writes a triple-index layout to the chosen
destination:

    <dst>/
        by-vendor/<vendor-slug>/<category-slug>/<doc-slug>-<period>.pdf
        by-institution/<institution-slug>/<vendor-slug>/<doc-slug>-<period>.pdf
        edge-cases/<scenario>/README.md
        manifest.json
        README.md  (left alone if it already exists)

The script is idempotent — re-running with the same ZIP overwrites the
sandbox in place.

Source ZIP filename pattern: ``Banco Docs Sample-*.zip``. The ZIP layout
is hardcoded against the May-2026 schema:

    Banco Docs Sample/<Vendor Display>/<Category>/<filename>.pdf

If the schema changes, update VENDOR_SLUG / VENDOR_PREFIX / CATEGORY_SLUG
at the top of this file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import defaultdict
from pathlib import Path

# Path constants
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_DST = REPO_ROOT.parent / "_reference" / "sample-docs"

VENDOR_SLUG = {
    "Human Medical Services HUMESE, S.C.": "human-medical-humese",
    "Master Clean Plus, S. de R.L. de C.V.": "master-clean-plus",
    "Ángel Elías García": "angel-elias-garcia",
}

VENDOR_DISPLAY = {
    slug: display for display, slug in VENDOR_SLUG.items()
}

VENDOR_RFC = {
    # Placeholder RFCs — replace with real ones if known.
    "human-medical-humese": "HMS-DEMO-RFC",
    "master-clean-plus": "MCP-DEMO-RFC",
    "angel-elias-garcia": "AEG-DEMO-RFC",
}

VENDOR_PREFIX = {
    "human-medical-humese": "HUMAN MED ",
    "master-clean-plus": "MASTER CLE ",
    "angel-elias-garcia": "ÁNGEL ELÍAS GARCÍA ",
}

CATEGORY_SLUG = {
    "SAT": "sat",
    "IMSS": "imss",
    "INFONAVIT": "infonavit",
    "Acuses": "acuses",
}

INSTITUTION_FOR_CATEGORY = {
    "sat": "sat",
    "imss": "imss",
    "infonavit": "infonavit",
    # Acuses (ICSOE / SISUB) are filed against STPS/REPSE.
    "acuses": "stps_repse",
}

MONTH_INDEX = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}

DEFAULT_YEAR = 2025

DOC_TYPES: list[tuple[str, str, str]] = [
    # (matcher, slug, label) — first match wins.
    ("acuse sisub",                  "acuse-sisub",                       "Acuse SISUB"),
    ("acuse icsoe",                  "acuse-icsoe",                       "Acuse ICSOE"),
    ("comp. de pago bancario",       "comp-pago-bancario",                "Comprobante de pago bancario"),
    ("comp. entero de pago iva",     "comp-entero-pago-iva",              "Comprobante entero de pago IVA"),
    ("comp. entero de pago isr",     "comp-entero-pago-isr",              "Comprobante entero de pago ISR"),
    ("cfdi de pago de cuotas",       "cfdi-pago-cuotas",                  "CFDI de pago de cuotas"),
    ("cuotas obrero patronales",     "cuotas-obrero-patronales",          "Cuotas obrero-patronales"),
    ("resumen liquidación",          "resumen-liquidacion",               "Resumen de liquidación"),
    ("declaración iva",              "declaracion-iva",                   "Declaración IVA"),
    ("declaración isr por retención","declaracion-isr-retencion",         "Declaración ISR por retención de sueldos y salarios"),
    ("comps. nómina trabajadores",   "comprobantes-nomina-trabajadores",  "Comprobantes de nómina de trabajadores"),
]


def slugify(value: str) -> str:
    norm = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()


def detect_doc_type(name_lower: str) -> tuple[str, str]:
    for matcher, slug, label in DOC_TYPES:
        if matcher in name_lower:
            return slug, label
    raise ValueError(f"No doc-type matcher hit for: {name_lower}")


def detect_month(name_lower: str) -> tuple[int, str]:
    for spanish, idx in MONTH_INDEX.items():
        if spanish in name_lower:
            return idx, spanish
    raise ValueError(f"No month token found in: {name_lower}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def extract_zip(zip_path: Path, dest: Path) -> Path:
    """Extract a ZIP using macOS ditto (Unicode-safe) and return the root dir."""
    subprocess.run(["ditto", "-xk", str(zip_path), str(dest)], check=True)
    roots = [p for p in dest.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(
            f"Expected exactly one top-level dir in the ZIP, got: {roots}"
        )
    return roots[0]


def build(src_root: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    (dst / "by-vendor").mkdir()
    (dst / "by-institution").mkdir()
    (dst / "edge-cases").mkdir()

    manifest: list[dict] = []
    files_by_vendor: dict[str, list[str]] = defaultdict(list)

    for src_file in sorted(src_root.rglob("*.pdf")):
        rel = src_file.relative_to(src_root)
        vendor_display, category_display, filename = rel.parts
        vendor_slug = VENDOR_SLUG[vendor_display]
        category_slug = CATEGORY_SLUG[category_display]
        institution_slug = INSTITUTION_FOR_CATEGORY[category_slug]

        bare = filename.removeprefix(VENDOR_PREFIX[vendor_slug]).removesuffix(".pdf")
        bare_lower = bare.lower()

        doc_slug, doc_label = detect_doc_type(bare_lower)
        month_idx, month_es = detect_month(bare_lower)
        period_key = f"{DEFAULT_YEAR}-M{month_idx:02d}"
        norm_name = f"{doc_slug}-{period_key}.pdf"

        vendor_dir = dst / "by-vendor" / vendor_slug / category_slug
        vendor_dir.mkdir(parents=True, exist_ok=True)
        vendor_path = vendor_dir / norm_name
        counter = 1
        while vendor_path.exists():
            vendor_path = vendor_dir / f"{doc_slug}-{period_key}-{counter}.pdf"
            counter += 1
        shutil.copy2(src_file, vendor_path)

        institution_dir = dst / "by-institution" / institution_slug / vendor_slug
        institution_dir.mkdir(parents=True, exist_ok=True)
        institution_path = institution_dir / vendor_path.name
        shutil.copy2(src_file, institution_path)

        files_by_vendor[vendor_slug].append(vendor_path.name)
        manifest.append({
            "filename": vendor_path.name,
            "vendor_slug": vendor_slug,
            "vendor_display": VENDOR_DISPLAY[vendor_slug],
            "vendor_rfc": VENDOR_RFC[vendor_slug],
            "category_slug": category_slug,
            "category_display": category_display,
            "institution_code": institution_slug,
            "doc_type_slug": doc_slug,
            "doc_type_label": doc_label,
            "period_key": period_key,
            "period_month_es": month_es,
            "period_year": DEFAULT_YEAR,
            "by_vendor_path": str(vendor_path.relative_to(dst)),
            "by_institution_path": str(institution_path.relative_to(dst)),
            "size_bytes": src_file.stat().st_size,
            "sha256": sha256_of(src_file),
            "source_filename": filename,
        })

    manifest.sort(key=lambda r: (r["vendor_slug"], r["category_slug"], r["filename"]))

    out = {
        "generated_from": "Banco Docs Sample-*.zip",
        "default_year": DEFAULT_YEAR,
        "vendors": [
            {
                "slug": slug,
                "display": display,
                "rfc": VENDOR_RFC[slug],
                "file_count": len(files_by_vendor[slug]),
            }
            for slug, display in VENDOR_DISPLAY.items()
        ],
        "categories": [
            {"slug": "sat", "label": "SAT"},
            {"slug": "imss", "label": "IMSS"},
            {"slug": "infonavit", "label": "INFONAVIT"},
            {"slug": "acuses", "label": "Acuses (STPS/REPSE)"},
        ],
        "files": manifest,
        "total_files": len(manifest),
    }
    (dst / "manifest.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    edge_case_hints = {
        "valid": (
            "Clean documents per vendor. Already mirrored in by-vendor/. "
            "Use these for happy-path upload tests."
        ),
        "invalid": (
            "Drop intentionally broken samples here: corrupted PDFs (random "
            "bytes), encrypted PDFs, oversized (>15 MB), non-PDF disguised, "
            "zero-byte files. Name them so the failure mode is obvious, "
            "e.g. corrupt-bytes.pdf, encrypted-locked.pdf, oversized-50mb.pdf."
        ),
        "mismatched-period": (
            "Drop documents whose visible period does not match the "
            "period_key the wizard will send. Exercises the "
            "document_intelligence mismatch_reason path."
        ),
    }
    for scenario, hint in edge_case_hints.items():
        d = dst / "edge-cases" / scenario
        d.mkdir(exist_ok=True)
        (d / "README.md").write_text(
            f"# `edge-cases/{scenario}/`\n\n{hint}\n", encoding="utf-8"
        )

    _write_root_readme(dst)

    print(f"Built sandbox at {dst}")
    print(f"  vendors        : {len(VENDOR_DISPLAY)}")
    print(f"  total files    : {len(manifest)}")


def _write_root_readme(dst: Path) -> None:
    (dst / "README.md").write_text(
        """# Sample documents sandbox

40 real-shape PDFs across 3 vendors × 4 institutions, normalized into a
triple-index layout so manual testing, automated fixtures, and the
upload wizard can all consume the same source.

Built from a `Banco Docs Sample-*.zip` by
`scripts/reports/build_sample_sandbox.py` in the CheckWise repo. Re-run
that script if the source ZIP changes.

## Layout

```
sample-docs/
├── manifest.json                  ← canonical mapping
├── by-vendor/                     ← navigate by vendor first
│   ├── angel-elias-garcia/{sat,imss,infonavit,acuses}/
│   ├── human-medical-humese/{sat,imss,infonavit,acuses}/
│   └── master-clean-plus/{sat,imss,infonavit,acuses}/
├── by-institution/                ← same files, mirrored
│   ├── sat/<vendor>/
│   ├── imss/<vendor>/
│   ├── infonavit/<vendor>/
│   └── stps_repse/<vendor>/       ← acuses (ICSOE / SISUB) are STPS filings
└── edge-cases/
    ├── valid/                     ← happy-path (already in by-vendor)
    ├── invalid/                   ← corrupt / encrypted / oversized / non-PDF
    └── mismatched-period/         ← period mis-matches the wizard
```

The two index trees hold independent copies, not symlinks.

## Filename convention

`<doc-type-slug>-<period-key>.pdf` — e.g. `acuse-icsoe-2025-M09.pdf`.
Period keys use the canonical CheckWise format `YYYY-Mxx`.

## `manifest.json`

Every entry maps a file to: vendor (slug + display + RFC), category,
institution code, doc type (slug + label), period (key + month + year),
by-vendor + by-institution paths, size, sha256, and the original
mojibake-prone source filename for traceability.

Automated tests should read `manifest.json` and never rely on filename
parsing.

## Rebuilding

```bash
python3 scripts/reports/build_sample_sandbox.py /path/to/Banco\\ Docs\\ Sample-*.zip
```

Or, from a non-default location:

```bash
python3 scripts/reports/build_sample_sandbox.py /path/to/zip.zip --dst /custom/sample-docs
```

The script overwrites the destination in place.
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the CheckWise sample-docs sandbox from a ZIP.")
    parser.add_argument("zip_path", type=Path, help="Path to the Banco Docs Sample ZIP.")
    parser.add_argument(
        "--dst",
        type=Path,
        default=DEFAULT_DST,
        help=f"Destination dir (default: {DEFAULT_DST}).",
    )
    args = parser.parse_args()

    if not args.zip_path.is_file():
        parser.error(f"ZIP not found: {args.zip_path}")

    with tempfile.TemporaryDirectory(prefix="checkwise-samples-") as tmp:
        tmp_path = Path(tmp)
        src_root = extract_zip(args.zip_path, tmp_path)
        build(src_root, args.dst)


if __name__ == "__main__":
    main()
