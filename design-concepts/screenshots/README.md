# `design-concepts/screenshots/` — Current-state PNGs

Captured 2026-05-17 during the Phase 1 audit (`design/audit-2x` branch, V2.0 baseline).

## Folders

- `public/` — Headless-Chrome captures of unauthenticated routes (`/`, `/login`, `/admin/login`, `/activate?token=demo`). All at 1440×900.
- `portal/`, `admin/`, `client/` — Reserved for authenticated captures. **Empty today** because saving authenticated PNGs to disk requires either replaying the auth flow under headless Chrome with the session cookie, or wiring CDP into the preview's Chromium. Audit observations of those routes were captured inline during the Phase 1 session and recorded directly in [`docs/design-system/AUDIT_2_X.md`](../../docs/design-system/AUDIT_2_X.md). Pre-Phase 5 we should automate this capture step (Playwright script with seeded creds + per-route screenshot loop) so future audits ship full PNG sets.

## Use

These are the "before" reference for the 2.x visual rework. Don't edit. Re-capture from a clean dev stack when needed.

```bash
# Re-capture public routes (1 minute, no auth):
cd <repo>
docker compose up -d postgres
bash backend/scripts/dev_setup.sh
(cd frontend && npm run dev) &
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for route in "/" "/login" "/admin/login" "/activate?token=demo"; do
  safe=$(echo "$route" | sed 's|[^a-zA-Z0-9]|_|g; s|^_||')
  [ -z "$safe" ] && safe="root"
  "$CHROME" --headless=new --hide-scrollbars --window-size=1440,900 \
    --screenshot="design-concepts/screenshots/public/${safe}.png" \
    "http://localhost:3000${route}"
done
```

For authenticated captures, see the TODO above.
