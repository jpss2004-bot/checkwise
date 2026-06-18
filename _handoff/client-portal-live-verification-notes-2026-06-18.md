# Client Portal — Live Verification Notes (2026-06-18)

Captured by driving the running local stack (web :3000, API :8000, Postgres :5432)
as `cliente.demo@checkwise.mx` (org "Operadora Multinacional · Demo", 3 providers,
all `red`/en riesgo, 5% compliance). These are observations only the live app
reveals — to be merged into the synthesized audit report.

## Baseline (good)
- **Zero console errors/warnings** on dashboard, vendors, calendar, vendor-detail.
- **Token discipline is excellent**: `grep` finds 0 raw hex and 0 raw Tailwind color
  literals (`text-gray-500` etc.) across `app/client/**` — everything uses semantic vars.
- Desktop IA is strong: horizontal 8-item nav, BackBar, dense data tables, KPI strips.
- Mobile reflows correctly (calendar KPI cards → 2-col grid; filter chips wrap).
- Providers list is enterprise-grade: KPI strip + search + semáforo filter + a 10-column
  table (semáforo, % cumplimiento, en revisión, faltantes, por corregir, por vencer,
  renovación, novedades + Reporte/Ver actions).
- Calendar is excellent: KPI cards (VENCIDAS 192, próximo vencimiento 17-jul), institution
  filter chips (Todas 417 / SAT 183 / IMSS 144 / INFONAVIT 72 / STPS-REPSE 18) + provider
  chips, providers×12-months risk grid with per-cell counts + overdue icons.
- Vendor detail is comprehensive: compliance donut, multi-segment "DOCUMENTOS POR ESTADO"
  donut (148 docs split Aprobados/En revisión/Necesita aclaración/Requiere corrección/
  Vencidos/Por entregar), contratos section, próximos vencimientos.

## Live findings (merge into report)
1. **[Content/Copy — High-confidence, S]** Dashboard empty state has missing Spanish
   accents: `app/client/dashboard/page.tsx:616` → "Cuando un proveedor suba documentos o
   haya avances, apareceran aqui." should be "aparecerán aquí." (CheckWise voice = precise,
   Spanish-first.)
2. **[UI/DataViz — Medium]** Dashboard hero is sparse: a large "5%" ring with a tiny red
   arc and a wide empty right half. The compliance % donut at low values reads as a nearly
   empty gray ring — low visual weight vs the "critical" status it represents.
3. **[DataViz/Consistency — Medium]** Two donuts on the dashboard encode overlapping info
   (hero compliance ring + "DISTRIBUCIÓN DE TU PORTAFOLIO" ring = 100% en riesgo). The
   richer multi-segment donut on vendor-detail ("DOCUMENTOS POR ESTADO") is far more
   informative than the single-arc % rings — donut treatment is inconsistent across surfaces.
4. **[DataViz — Medium, verify in code]** Vendor detail "EXPEDIENTE INICIAL · 0%" progress
   bar renders as a FULL-WIDTH gold/amber bar despite "0 / 5" — looks ~100% filled when it
   is 0%. Likely the empty track is colored, or the fill width is inverted. File:
   `app/client/vendors/[vendor_id]/page.tsx` (expediente progress bar).
5. **[ExecutiveReadability/Consistency — High]** Cross-surface metric reconciliation: the
   dashboard headlines "387 faltantes obligatorios," the calendar headlines "VENCIDAS 192"
   and "Todas 417" obligations, and vendor-detail says "7 DE 144 OBLIGACIONES AL DÍA." Each
   surface uses a different denominator/label with no shared definition or cross-link. A CFO
   /Sponsor cannot reconcile "387 vs 192 vs 417" — needs one canonical headline metric +
   consistent labels.
6. **[Responsiveness — Low/Medium]** WISE dock button is clipped off the right edge at
   375px (mobile). It hangs partially off-screen over content.
7. **[UX — Low]** The "Reportar" feedback FAB (bottom-right) overlaps the right-most table
   action button ("Ver") on the providers list at desktop, partially covering it.
8. **[UX/Actionability — verify]** Calendar "VENCIDAS 192" is a large alarming red number
   with no obvious single next-action ("ver los 192 vencidos" / bulk drill-in). Confirm
   whether the KPI card is clickable.

Login for re-verification: `cliente.demo@checkwise.mx` / `ClienteDemo!2026` (client_admin).
Inject session into localStorage key `checkwise.admin.session.v1` after POST /api/v1/auth/login.
