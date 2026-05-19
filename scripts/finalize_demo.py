#!/usr/bin/env python3
"""Mix silent demo video + voice-over MP3s + background music → final MP4.

Pipeline:
  1. Concatenate the per-scene voice MP3s with brief silences between
     them, ordered by SCRIPT in scripts/demo_script.py. Each scene's
     audio starts at the same wall-clock the recorded video shows that
     scene (the recording script aligns dwell to narration duration +
     SCENE_TAIL = 0.6s, so we mirror that here).
  2. Generate a subtle background ambient pad sized to match the video
     duration, with a 3s fade-in and a 3s fade-out. The pad is the
     fallback for when no royalty-free track is dropped in at
     docs/audit-screenshots/2026-05-18-system-audit/music.mp3 — if
     that file exists, we use it instead.
  3. Composite:
        silent video + voice (at 0 dB) + music (ducked under voice)
     Output:
        docs/audit-screenshots/2026-05-18-system-audit/demo.mp4
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from demo_script import SCRIPT  # noqa: E402

OUT_DIR = ROOT / "docs" / "audit-screenshots" / "2026-05-18-system-audit"
VOICE_DIR = OUT_DIR / "voice"
SILENT_MP4 = OUT_DIR / "demo.silent.mp4"
USER_MUSIC = OUT_DIR / "music.mp3"
GENERATED_MUSIC = OUT_DIR / "_music.generated.m4a"
VOICE_CONCAT = OUT_DIR / "_voice.concat.m4a"
FINAL_MP4 = OUT_DIR / "demo.mp4"

# Must match SCENE_TAIL in scripts/record_demo.py — the silence
# between scenes in the concatenated voice track lets the on-screen
# action breathe after each narration line.
INTER_SCENE_SILENCE = 0.6


def must(cmd: list[str]) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(f"\n✗ ffmpeg failed:\n{' '.join(cmd)}\n{res.stderr[-2000:]}\n")
        res.check_returncode()
    return res


def probe_duration(path: Path) -> float:
    return float(
        subprocess.check_output(
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
    )


def build_voice_track() -> Path:
    """Concat scene MP3s with INTER_SCENE_SILENCE gaps."""
    print("→ Building voice-over track")
    # Use a concat demuxer file with adelay-style silence between clips
    inputs: list[str] = []
    filters: list[str] = []
    for i, (scene_id, _text) in enumerate(SCRIPT):
        clip = VOICE_DIR / f"{scene_id}.mp3"
        if not clip.exists():
            raise SystemExit(f"missing voice clip: {clip}")
        inputs += ["-i", str(clip)]
    # Use the anullsrc + concat trick to insert silence between clips.
    # Build a filter graph: [0:a][silence][1:a][silence][2:a]...concat
    n = len(SCRIPT)
    silence_filter = (
        f"anullsrc=channel_layout=mono:sample_rate=24000,"
        f"atrim=duration={INTER_SCENE_SILENCE}[sil]"
    )
    parts: list[str] = []
    parts.append(silence_filter)
    chain: list[str] = []
    for i in range(n):
        chain.append(f"[{i}:a]")
        if i < n - 1:
            chain.append("[sil]")
    # The silence filter only produces one segment; we need a copy per gap
    # — duplicate via asplit.
    # Easier: build atrim'd silences inline per gap.
    # Replace with a cleaner approach using delays.
    parts = []
    seg_labels: list[str] = []
    cursor = 0.0
    delay_chain: list[str] = []
    for i, (scene_id, _) in enumerate(SCRIPT):
        clip = VOICE_DIR / f"{scene_id}.mp3"
        dur = probe_duration(clip)
        # adelay needs ms; cursor is the seconds offset for this clip
        delay_ms = int(cursor * 1000)
        delay_chain.append(
            f"[{i}:a]adelay={delay_ms}|{delay_ms},apad=pad_dur=0[d{i}]"
        )
        seg_labels.append(f"[d{i}]")
        cursor += dur + INTER_SCENE_SILENCE
    filter_complex = ";".join(delay_chain) + ";" + "".join(seg_labels) + (
        f"amix=inputs={n}:duration=longest:dropout_transition=0,"
        f"aresample=async=1:first_pts=0,"
        f"asetpts=PTS-STARTPTS[a]"
    )
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[a]",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        str(VOICE_CONCAT),
    ]
    must(cmd)
    dur = probe_duration(VOICE_CONCAT)
    print(f"  ✓ {VOICE_CONCAT.name}  {dur:.1f}s")
    return VOICE_CONCAT


def generate_music(video_duration: float) -> Path:
    """Synthesize a subtle ambient pad matching the video duration.

    Two detuned sine partials a perfect fifth apart (A3 + E4 ≈ 220Hz +
    330Hz) with a long echo for an ambient tail. Heavy low-pass to
    soften, fade-in/fade-out, normalized low. The pad is intentionally
    NOT musical — it's just a tone bed so the silence between voice
    lines doesn't feel dead.

    Drop a real royalty-free track at docs/audit-screenshots/
    2026-05-18-system-audit/music.mp3 to override this generator.
    """
    print("→ Generating ambient pad")
    fade_out_start = max(0.0, video_duration - 3.0)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=220:duration={video_duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency=329.63:duration={video_duration}",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={video_duration}",
        "-filter_complex",
        (
            "[0:a]volume=0.6[a0];"
            "[1:a]volume=0.4[a1];"
            "[2:a]volume=0.18[a2];"
            "[a0][a1][a2]amix=inputs=3:duration=longest[mix];"
            "[mix]"
            "lowpass=f=900,"
            "aecho=0.7:0.85:60|120|240:0.4|0.3|0.2,"
            f"afade=t=in:st=0:d=3,"
            f"afade=t=out:st={fade_out_start}:d=3,"
            "loudnorm=I=-30:TP=-3:LRA=11[a]"
        ),
        "-map", "[a]",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        "-ac", "2",
        str(GENERATED_MUSIC),
    ]
    must(cmd)
    print(f"  ✓ {GENERATED_MUSIC.name}")
    return GENERATED_MUSIC


def composite(video: Path, voice: Path, music: Path) -> Path:
    """Final mux: video + (voice at 0 dB + music ducked to -22 dB)."""
    print("→ Compositing final MP4")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(voice),
        "-i", str(music),
        "-filter_complex",
        (
            # Voice at full level, split into two copies — one for the
            # final mix, one for the sidechain key. ffmpeg 8 disallows
            # reusing the same labeled pad on two filter inputs.
            "[1:a]volume=1.0,asplit=2[voiceMix][voiceKey];"
            # Music significantly quieter
            "[2:a]volume=0.22[bed];"
            # Duck music under voice
            "[bed][voiceKey]sidechaincompress="
            "threshold=0.05:ratio=8:attack=20:release=300:makeup=1[bedducked];"
            # Final mix
            "[voiceMix][bedducked]amix=inputs=2:duration=first:dropout_transition=0[a]"
        ),
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(FINAL_MP4),
    ]
    must(cmd)
    return FINAL_MP4


def main() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg/ffprobe not on PATH; brew install ffmpeg")
    if not SILENT_MP4.exists():
        raise SystemExit(
            f"{SILENT_MP4} missing — run scripts/record_demo.py first."
        )

    video_dur = probe_duration(SILENT_MP4)
    print(f"Silent video: {video_dur:.1f}s\n")

    voice = build_voice_track()

    if USER_MUSIC.exists():
        print(f"→ Using user-supplied music: {USER_MUSIC.name}")
        music = USER_MUSIC
    else:
        music = generate_music(video_dur)

    out = composite(SILENT_MP4, voice, music)

    dur = probe_duration(out)
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"\n✓ {out.relative_to(ROOT)}  ({dur:.1f}s · {size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
