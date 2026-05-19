#!/usr/bin/env python3
"""Generate Spanish voice-over MP3 clips for the CheckWise demo.

Reads scripts/demo_script.py and produces one MP3 per scene, plus a
JSON manifest with each clip's actual duration in seconds. The
manifest is consumed by scripts/record_demo.py to time each scene's
on-screen dwell to the narration.

Output:
  docs/audit-screenshots/2026-05-18-system-audit/voice/<scene>.mp3
  docs/audit-screenshots/2026-05-18-system-audit/voice/manifest.json
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from demo_script import PITCH, RATE, SCRIPT, VOICE  # noqa: E402

OUT_DIR = ROOT / "docs" / "audit-screenshots" / "2026-05-18-system-audit" / "voice"
OUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST = OUT_DIR / "manifest.json"


async def synth(scene_id: str, text: str, out: Path) -> None:
    """Render one scene's audio via edge-tts."""
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
    await communicate.save(str(out))


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


async def main() -> None:
    durations: dict[str, float] = {}
    print(f"Voice: {VOICE} · rate={RATE} · pitch={PITCH}")
    print(f"Scenes: {len(SCRIPT)}\n")
    for scene_id, text in SCRIPT:
        out = OUT_DIR / f"{scene_id}.mp3"
        await synth(scene_id, text, out)
        dur = probe_duration(out)
        durations[scene_id] = dur
        size_kb = out.stat().st_size // 1024
        print(f"  ✓ {scene_id:24s} {dur:5.2f}s  ({size_kb} KB)")

    MANIFEST.write_text(
        json.dumps(
            {
                "voice": VOICE,
                "rate": RATE,
                "pitch": PITCH,
                "durations": durations,
                "total": round(sum(durations.values()), 2),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    total = sum(durations.values())
    print(f"\n✓ Total narration: {total:.1f}s ({total/60:.1f} min)")
    print(f"✓ Manifest: {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
