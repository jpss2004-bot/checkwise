# CheckWise — Notas de arquitectura a futuro

Cada sección separa **(A) qué existe hoy** de **(B) qué construir
después** y **(C) qué no sobre-construir aún**. La idea es preparar
el terreno para los próximos sprints sin sobrediseñar nada antes de
Monday.

---

## 1. Notificaciones

### A. Hoy
- Tabla `provider_notifications` y `client_notifications` con campos
  `severity ∈ {green,yellow,red,info}`, `read_at`, `action_url`,
  `payload`, `notification_type`, `submission_id`/`vendor_id` opcional.
- Disparadores: reviewer decision → provider, provider upload → client,
  renewal threshold cross → ambos.
- UI: `/portal/notifications` y `/client/notifications` con semáforo
  por color, agrupación por día, marca-leído, deep links.

### B. Construir después
- **Outbox pattern** para transporte externo: añadir tabla
  `notification_dispatches` con `(notification_id, channel, status,
  attempts, last_error)`; channels `inapp|email|whatsapp`.
- **Worker** `python -m scripts.run_notification_dispatch` que tome
  notifications pendientes y entregue por canal según
  `User.contact_preference`.
- **Idempotencia**: usar el mismo patrón que `RenewalReminder`
  (unique constraint sobre `(notification_id, channel)`).
- **Acuse de lectura** vía `read_at` + un endpoint
  `POST /notifications/{id}/read`.

### C. No sobre-construir
- No introducir aún un broker (Redis/SQS). Worker via cron Render es
  suficiente hasta volumen >10k notifications/día.
- No usar webhooks externos genéricos; cada canal tiene su patrón.

---

## 2. WhatsApp y email recordatorios

### A. Hoy
- `services/email_delivery.py` sólo se usa para password reset.
- WhatsApp: cero código. Sólo un componente `SupportCard` huérfano.
- Las notificaciones de renovación y decisión sólo viven in-app.

### B. Construir después

**Capa de transporte**:
```
app/services/notification_transports/
  __init__.py
  base.py        # TransportProtocol
  email.py       # SES o SendGrid
  whatsapp.py    # Cloud API (Meta) o BSP
```

- `base.py` define `class Transport(Protocol)` con `send(notif) -> Result`.
- `email.py` envuelve la implementación actual.
- `whatsapp.py` arranca contra **Meta Cloud API** (no Twilio): es la
  vía oficial y los templates aprobados son obligatorios para
  notificaciones outbound iniciadas por el sistema.

**Templates aprobados (HSM)** — qué pedirle a Meta:
1. `renewal_due_soon` ({{1}} dias para {{2}} - {{3}}).
2. `renewal_overdue` ({{1}} - {{2}} requiere acción).
3. `document_rejected` ({{1}} fue rechazado: {{2}}).
4. `document_approved` ({{1}} fue aprobado).

**Configuración**:
- `WHATSAPP_PHONE_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_TEMPLATE_NS`
  en Render secrets.
- `User.contact_preference` ya existe y soporta `email|whatsapp|both`.

**Rate limit y costo**:
- Templates HSM cobran por entrega; cap por usuario diario (≤3/día)
  para evitar facturas inesperadas.

### C. No sobre-construir
- No implementar un IVR o conversational layer; el primer hito es
  transactional outbound.
- No mezclar Soporte (`SupportCard` con QR) con el transporte de
  notificaciones: son productos distintos.

---

## 3. Metadata y tags

### A. Hoy
- `DocumentInspection` guarda `detected_institution`,
  `detected_document_type`, `detected_rfcs[]`, `detected_dates[]`,
  `period_mentions[]`, `raw_metadata{}`, `mismatch_reason`.
- `services/client_metadata.py` produce un XLSX por cliente con
  metadata por documento.
- `/client/metadata` permite búsqueda full-text local sobre el preview
  del XLSX.

### B. Construir después

**Tag vocabulary**:
- Definir un vocabulario controlado de tags (~30 conceptos: institución,
  tipo de documento, periodicidad, fecha clave, contraparte, etc.).
- Crear tabla `document_tags` con `(document_id, tag, source, confidence)`.
  - `source ∈ {detector,manual,ai}` para trazar origen.
- Mantener `raw_metadata` para retrocompatibilidad; los tags son una
  capa sobre la inspección.

**Búsqueda**:
- Endpoint `GET /api/v1/metadata/search?client_id=...&q=...&tags=...`
  con paginación.
- Postgres FTS (`tsvector` sobre `original_filename + raw_metadata
  jsonb_path_query_text` + array de tags) — sin Elasticsearch.

**"Fecha principal"** del documento (la junta lo mencionó):
- Heurística: para cada `detected_document_type` definir cuál de las
  `detected_dates` es la "main date" (CSF → fecha de emisión; OPI →
  periodo de aplicación). Implementar en
  `services/document_intelligence.py:_resolve_main_date(doc_type, dates)`.
- Guardar `main_date` denormalizado en `DocumentInspection`.

### C. No sobre-construir
- No usar vector DB ni embeddings ahora; FTS sobre tags + metadata
  cubre 80% de los queries.
- No exponer tag editing al cliente hasta que el vocabulario esté
  estable.

---

## 4. Renewal engine

### A. Hoy
- `RenewalReminder` con unique constraint
  `(workspace_id, requirement_code, cycle_anchor_date, threshold_days)`.
- Cron Render diario 14:00 UTC = 08:00 CDMX (`render.yaml:170-189`).
- Thresholds severidad: 30/14/7 amarillo, 0/-7/-14/-21/-28 rojo.
- Sólo CSF, REPSE, registro patronal hoy.

### B. Construir después
- **Pluggable thresholds por requirement_code** — hoy hardcoded.
  Mover a una tabla `requirement_renewal_rules` con
  `(requirement_code, cycle_days, thresholds_yellow[], thresholds_red[])`.
- **Recovery view** `/admin/renewals` que muestre el último run, los
  reminders emitidos en las últimas 7 fechas y los que faltan por
  emitir.
- **Backfill on enrollment** — si un workspace entra a la plataforma
  con un CSF de hace 60 días, hoy el cron sólo dispara el threshold
  cuando lo cruza. Añadir un "catch-up emit at first enrollment".

### C. No sobre-construir
- No reescribir `renewal_dispatch.py` para que sea event-driven;
  el cron diario es suficiente.

---

## 5. AI bug triage (Phase 2+)

> La junta pidió **diseño**, no implementación.

### A. Hoy
- `feedback_reports` row con descripción, captura, console logs, URL,
  user agent, viewport, user roles.
- Slack delivery en background. Admin triage queue manual.

### B. Pipeline a futuro
1. **Ingest** — un evento `feedback.created` con el `feedback_id`
   despierta un worker.
2. **Context gather** — el worker baja la captura, los logs, la URL y
   abre el código relevante (mapeando `url.path` → `apps/web/app/...`).
3. **Compare** — un LLM (Claude Opus / Sonnet con prompt caching
   sobre el repo) analiza el bug y propone una hipótesis.
4. **Duplicate detection** — comparar embedding del bug nuevo contra
   bugs históricos en `feedback_reports`. Marcar como "duplicate of
   #N" si la similitud > 0.85.
5. **Suggest fix** — el LLM produce (a) reproducción mínima, (b) diff
   propuesto.
6. **Approval gate** — el admin abre `/admin/feedback-reports/[id]`
   y ve la sugerencia. Si aprueba, se crea un PR via `gh pr create`.
7. **Audit log** — cada paso escribe a `audit_log`.

### C. No sobre-construir
- No implementar nada de esto hasta que haya 100+ bugs reales en
  `feedback_reports`. Antes de eso, la heurística humana es más
  barata y precisa.
- No autoaplicar diffs; siempre requerir aprobación humana.

---

## 6. Descargas

### A. Hoy
- `services/expediente_zip.py` produce ZIP por workspace con filtros
  `status`, `period_key`, `institution`. Caps: 200 archivos, 500 MB.
- Audit row `provider.document_downloaded` por descarga individual.
- UI: provider (calendario), cliente (vendor detail).

### B. Construir después
- **ZIP admin-side**: botón en `/admin/vendors/[id]` que use el mismo
  endpoint con guard `internal_admin`.
- **Async generation** para ZIPs >100MB: hoy es `StreamingResponse`
  síncrono. Mover a `ReportExport`-style (pendiente → ready) con
  notification cuando esté listo.
- **Filters UI** en cliente: añadir un panel
  (Periodo / Institución / Estado) que componga la URL del ZIP.

### C. No sobre-construir
- No usar AWS Glue / Athena. Los expedientes son archivos planos.

---

## 7. Deep-link calendario → upload

### A. Hoy
- `/portal/calendar` clickea, abre drawer, drawer route a
  `/portal/upload?requirement=...&requirement_code=...&institution=...&period_key=...&period_label=...&replaces=...&from=onboarding`.
- El wizard prefilla esos campos automáticamente.

### B. Construir después
- **Réplica en `/client/calendar`** — hoy es agregado mensual sin
  drill-down. Añadir vista por proveedor con la misma mecánica de drawer.
- **Deep-link desde notificaciones** — la mayoría ya tiene
  `action_url`, validar 1:1 que rutean al lugar correcto.

### C. No sobre-construir
- No introducir un nuevo router; el query-string es suficiente.

---

## 8. Admin review workflow

### A. Hoy
- `ReviewerAction ∈ {approve,reject,request_clarification,mark_exception}`.
- Submitir decision escribe `DocumentStatusHistory`, `ValidationEvent`,
  `AuditLog`, y crea `ProviderNotification`.
- Observaciones (`observations`) se guardan en `AuditLog.metadata`.

### B. Construir después
- **PDF inline preview en admin** (cubierto en P0-5 del fix plan).
- **Filtros UI completos**: provider / client / institución / periodo
  / estado en `/admin/reviewer` (hoy sólo status + institución).
- **Bulk action** — seleccionar múltiples submissions y aplicar la
  misma decisión (sólo `approve` cuando todas pasan automated checks).
- **Re-asignación** — un reviewer puede pasar un caso a otro reviewer
  con motivo. Requiere campo `assigned_to_user_id` en `Submission`.

### C. No sobre-construir
- No introducir un workflow engine. El estado actual del state machine
  está bien definido y los hooks ya emiten audit log.

---

## 9. Auto-onboarding del cliente post-pago

### A. Hoy
- No existe form self-service para cliente nuevo.
- Admin tiene `ClientForm` manual sin email.

### B. Construir después

Opción A — **link de invitación tokenizado**:
1. Cuando el cliente paga, Stripe (o el provider de pago) envía webhook
   a `/api/v1/payments/stripe`.
2. El handler crea un `ClientInvitation` con `token_hash`, `expires_at`.
3. Email con link a `https://app.checkwise.mx/client/onboarding?token=...`.
4. La página pide RFC, email, nombre, persona del contacto. Submit
   crea el `Client` y la `Organization` correspondiente.

Opción B — **invitación manual desde admin**:
1. Admin captura email del cliente nuevo en `/admin/clients/new`.
2. Backend envía email con link tokenizado.
3. Cliente entra al mismo `/client/onboarding`.

Opción B es más barata para Monday + 1 semana. Migrar a A cuando haya
integración real con el cobro.

### C. No sobre-construir
- No construir un sistema de billing aún. Hoy el cobro vive fuera
  de la plataforma.

---

## 10. Roles, permisos y futuras incorporaciones

### A. Hoy
- `MembershipRole`: `internal_admin`, `reviewer`.
- `Organization.kind ∈ {internal, client, vendor}`.
- Provider portal usa `ProviderWorkspace` con access token (legacy V1.2).

### B. Construir después
- **`client_admin` rol** para que el cliente vea su propia
  `Organization`, vendors y submissions sin que sea LegalShelf staff.
  Hoy `/client/*` opera contra una sesión cliente, pero el rol
  formal no está modelado.
- **`reviewer_lead`** para asignación + reportes de queue.
- **Per-client scoping de admin** — hoy `internal_admin` ve todo;
  un admin podría tener visibilidad limitada a un subconjunto de
  clientes via `Membership(organization_id)`.

### C. No sobre-construir
- No introducir ACLs row-level granulares. RLS de Postgres puede venir
  más tarde si los datos crecen.

---

## 11. Observabilidad

### A. Hoy
- `AuditLog` por mutación.
- `WiseEvent` para analytics del dock.
- Render logs estándar.

### B. Construir después
- **Endpoint `/admin/audit-log/{client_id}`** ya existe; añadir
  exportación CSV y filtros por entity_type + action.
- **Slack alerting**: `slack_delivery_status='failed'` por >10 minutos
  debe alertar a `#checkwise-feedback`.
- **Metrics endpoint** `/metrics` (Prometheus-like) con queue depth,
  renewal misses, validation throughput. Opcional, no urgente.

### C. No sobre-construir
- No introducir Datadog ni Honeycomb aún. Render logs + Slack basta.

---

## 12. Resumen de decisiones que NO deben tomarse ahora

1. No introducir un broker de mensajes.
2. No introducir un vector DB para metadata.
3. No introducir embeddings para duplicate detection (esperar a 100+
   bug reports).
4. No introducir un workflow engine.
5. No migrar a Elasticsearch.
6. No introducir billing/payments en la plataforma.
7. No introducir ACLs row-level.
8. No autoaplicar diffs de AI bug triage.

Mantener la simplicidad operativa (FastAPI + Postgres + cron Render +
Next.js + R2) es lo que hace que el equipo de tres personas pueda
correr.
