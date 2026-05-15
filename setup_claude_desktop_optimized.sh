#!/usr/bin/env bash
set -euo pipefail

echo "== CheckWise Claude Code Desktop optimized permissions setup =="

if [ ! -d ".git" ]; then
  echo "ERROR: Run this from the root of the CheckWise git repository."
  echo "Example:"
  echo "cd /Users/josepablosamano/Desktop/Personal/legalshelf/checkwise/CheckWise"
  exit 1
fi

mkdir -p .claude

touch .gitignore
grep -qxF ".claude/settings.local.json" .gitignore || echo ".claude/settings.local.json" >> .gitignore

cat > .claude/settings.local.json <<'CLAUDE_LOCAL_SETTINGS'
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "alwaysThinkingEnabled": true,
  "permissions": {
    "defaultMode": "acceptEdits",
    "allow": [
      "Read(.)",
      "Edit(.)",
      "Write(.)",

      "Bash(pwd)",
      "Bash(ls*)",
      "Bash(find*)",
      "Bash(grep*)",
      "Bash(cat*)",

      "Bash(git status*)",
      "Bash(git diff*)",
      "Bash(git log*)",
      "Bash(git branch*)",

      "Bash(npm install*)",
      "Bash(npm run lint*)",
      "Bash(npm run typecheck*)",
      "Bash(npm run build*)",
      "Bash(npm run dev*)",

      "Bash(python -m venv*)",
      "Bash(python -m pytest*)",
      "Bash(pytest*)",
      "Bash(pip install -r requirements.txt*)",
      "Bash(ruff check*)",
      "Bash(ruff format*)",

      "Bash(alembic current*)",
      "Bash(alembic history*)",
      "Bash(alembic upgrade head*)",

      "Bash(uvicorn app.main:app*)",
      "Bash(./scripts/checkwise_safe_v1.sh*)",

      "Bash(mkdir -p*)",
      "Bash(touch*)",
      "Bash(chmod +x*)"
    ],
    "ask": [
      "Bash(git add*)",
      "Bash(git commit*)",
      "Bash(git checkout*)",
      "Bash(git switch*)",
      "Bash(git pull*)",
      "Bash(docker*)",
      "Bash(docker compose*)",
      "Bash(brew install*)",
      "Bash(brew upgrade*)"
    ],
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./**/.env)",
      "Read(./**/.env.*)",
      "Read(./secrets/**)",
      "Read(./private/**)",
      "Read(./credentials/**)",
      "Read(./**/credentials.json)",
      "Read(./**/*secret*)",
      "Read(./**/*token*)",
      "Read(./**/*key*)",

      "Bash(rm -rf *)",
      "Bash(git push*)",
      "Bash(git reset --hard*)",
      "Bash(git clean*)",
      "Bash(sudo *)",
      "Bash(curl * | sh)",
      "Bash(curl * | bash)",
      "Bash(wget * | sh)",
      "Bash(wget * | bash)",
      "Bash(npm publish*)",
      "Bash(vercel --prod*)"
    ]
  }
}
CLAUDE_LOCAL_SETTINGS

echo "Done."
echo ""
echo "Created:"
echo "- .claude/settings.local.json"
echo ""
echo "This is local-only and should not be committed."
echo ""
echo "Next steps inside Claude Code Desktop:"
echo "1. Open CheckWise in Claude Code."
echo "2. Accept/trust the workspace when prompted."
echo "3. Run: /status"
echo "4. Confirm .claude/settings.local.json is active."
echo "5. Run: /doctor"
echo ""
echo "Recommended session mode:"
echo "- Use acceptEdits for normal development."
echo "- Avoid bypassPermissions unless you are doing a disposable experiment."
