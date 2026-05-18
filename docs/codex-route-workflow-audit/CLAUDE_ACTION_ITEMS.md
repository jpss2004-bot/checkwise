# Claude Action Items — Route / Workflow / Redirect Audit

## P1 — Fix First

1. **Activation bypass:** `proveedor.demo@checkwise.mx` reaches `/activate`, but clicking “Cancelar e iniciar sesión de nuevo” routes into `/portal/entra-a-tu-espacio` with the temporary-password JWT. Clear the session on cancel and enforce `must_change_password` in protected route guards/API.
2. **Provider Reports create failure:** `/portal/reports` shows 3 provider presets, but “Usar plantilla” returns `403 {"detail":"User has no organization memberships."}` in the current running DB. Backfill/derive provider owning scope before continuing Provider-first Reports.

## P2 — Retest After P1

3. Verify provider-created report editor stays in PortalShell and print route works.
4. Reconcile boss demo dashboard messaging with `expediente_status=complete`; it still showed limited/initial-expediente language during browser QA.

## P3 — Cleanup

5. Remove `/admin/login` double-hop once all shells can route directly to `/login`.
6. Add stable accessible names to header logout buttons across admin/client shells.

## Green Areas

- Admin Reports R2 filters and template-to-editor flow work.
- Client Reports R2 filters, hidden audience filter, and client-facing gating work.
- API role safety checks passed for client/provider against admin/reviewer endpoints.
