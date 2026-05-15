#!/usr/bin/env bash
# Register the recommended subset of upstream Taste + Impeccable skills as
# Claude Code project skills.
#
# Why this script exists:
#   - The Taste/Impeccable upstream packages install into `.agents/skills/`
#     (untracked install-time output, pinned by `skills-lock.json`).
#   - Claude Code only auto-discovers skills under `.claude/skills/<name>/SKILL.md`.
#   - Without this bridge step the upstream skills exist on disk but are not
#     surfaced in the active Skill tool list, which means agents have to
#     read SKILL.md files manually instead of invoking via /<name>.
#
# This script symlinks the recommended subset from `.agents/skills/<name>` into
# `.claude/skills/<name>` so they become invocable. It is idempotent and safe:
# pre-existing symlinks pointing at the right target are left alone, and real
# files (non-symlinks) are never overwritten — an error is printed instead.
#
# Run order on a fresh checkout:
#   1. ./install_checkwise_claude_skills.sh        (CheckWise-prefixed skills)
#   2. (your Taste/Impeccable installer of choice) (.agents/skills/ contents)
#   3. ./scripts/register-design-skills.sh         (this script — bridge)
#
# Re-run any time `.agents/skills/` is refreshed.

set -euo pipefail

# Skills the CheckWise design doctrine recommends. Names must match the
# `.agents/skills/<name>` directories. Banned local adaptations
# (`/taste`, `/impeccable-ui`) are deliberately excluded; the upstream
# `gpt-taste` and `impeccable` have different names so they do not collide.
SKILLS=(
  gpt-taste
  design-taste-frontend
  high-end-visual-design
  redesign-existing-projects
  impeccable
)

# Resolve repo root from script location so the script works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AGENTS_DIR="$REPO_ROOT/.agents/skills"
CLAUDE_DIR="$REPO_ROOT/.claude/skills"

if [ ! -d "$AGENTS_DIR" ]; then
  echo "ERROR: $AGENTS_DIR does not exist." >&2
  echo "Install the upstream Taste/Impeccable packages first." >&2
  echo "See docs/claude/EXTERNAL_DESIGN_SKILLS.md for sources." >&2
  exit 1
fi

mkdir -p "$CLAUDE_DIR"

registered=()
already_ok=()
missing=()
conflicts=()

for skill in "${SKILLS[@]}"; do
  src="$AGENTS_DIR/$skill"
  dest="$CLAUDE_DIR/$skill"
  rel_src="../../.agents/skills/$skill"

  if [ ! -d "$src" ]; then
    missing+=("$skill")
    continue
  fi

  if [ -L "$dest" ]; then
    current_target="$(readlink "$dest")"
    if [ "$current_target" = "$rel_src" ]; then
      already_ok+=("$skill")
      continue
    fi
    # Symlink exists but points elsewhere. Replace it (the previous link is
    # ours to manage; non-symlink files are handled in the next branch).
    rm "$dest"
    ln -s "$rel_src" "$dest"
    registered+=("$skill (relinked)")
    continue
  fi

  if [ -e "$dest" ]; then
    # Real directory or file at the destination — never overwrite.
    conflicts+=("$skill")
    continue
  fi

  ln -s "$rel_src" "$dest"
  registered+=("$skill")
done

echo "== Design skill registration =="
echo
if [ "${#registered[@]}" -gt 0 ]; then
  echo "Registered:"
  for s in "${registered[@]}"; do echo "  + $s"; done
  echo
fi
if [ "${#already_ok[@]}" -gt 0 ]; then
  echo "Already registered:"
  for s in "${already_ok[@]}"; do echo "  = $s"; done
  echo
fi
if [ "${#missing[@]}" -gt 0 ]; then
  echo "Missing from .agents/skills/ (install upstream first):"
  for s in "${missing[@]}"; do echo "  ? $s"; done
  echo
fi
if [ "${#conflicts[@]}" -gt 0 ]; then
  echo "Skipped (real file/dir at destination — refused to overwrite):"
  for s in "${conflicts[@]}"; do echo "  ! .claude/skills/$s"; done
  echo "Resolve manually then re-run."
  echo
fi

echo "Registered skills will be invocable as /<name> in the next Claude Code session."
echo "Banned local adaptations /taste and /impeccable-ui are intentionally not registered."
