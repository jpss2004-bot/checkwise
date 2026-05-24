# CheckWise — Auditoría de preparación para Monday (testers reales)

Fecha del informe: 2026-05-24 (sábado).
Audiencia: Jose Pablo (LegalShelf), Paco, Beko, Isaac, equipo CheckWise.
Origen: notas de junta del viernes 2026-05-23.

> Esta auditoría se hizo leyendo código directamente, corriendo
> typecheck/build/tests, y validando ruta por ruta. Todo lo marcado
> como DONE tiene cita a archivo y línea. Lo que no se pudo verificar
> en código está marcado como **NO VERIFICADO** con explicación.

---

## 1. Resumen ejecutivo

CheckWise está **funcionalmente sólido** para una prueba con testers el
lunes: el backend pasa 922 tests (`pytest` 132s, 14 warnings, 0
failures), el frontend compila limpio (`npm run typecheck` y
`npm run build` sin errores en Next.js 15 + React 19), y los flujos
críticos del proveedor (legal consent, expediente, calendario,
upload con prevalidación, semáforo, notificaciones, reportes) están
operativos.

**Hay varios bordes de UX y un par de huecos funcionales** que el
viernes señalaron como prioritarios. Ninguno es un crash, pero
algunos pueden confundir al tester de 40-50 años no técnico que es
el público objetivo. Lo más urgente es:

1. La etiqueta `posible_mismatch` aparece como **"Posible mismatch"**
   en el dashboard del cliente y en otras superficies (mezcla
   español–inglés). Distintas pantallas usan **tres traducciones
   distintas** del mismo estado.
2. **El revisor admin no tiene visor PDF embebido**: aprueba/rechaza
   con sólo metadatos. Si Isaac/Paco entran a revisar el lunes, no
   podrán abrir el archivo desde la misma pantalla.
3. **La carga multi-archivo (contrato + anexo) existe pero está
   detrás de un flag apagado** (`MULTI_FILE_UPLOAD_ENABLED=false`).
   En este momento los testers verán "primary file" únicamente.
4. **El "tu nueva entrega entró en `pendiente_revision`" del wizard**
   muestra el valor de enum crudo dentro de un Badge (línea 1736 de
   `intake-wizard.tsx`). El tester verá literalmente
   `pendiente_revision`.
5. **No existe formulario de auto-registro de cliente post-pago**.
   La junta lo pidió. El admin tiene un form de alta manual con
   Nombre/RFC/Responsable/Estado, pero **falta el campo email**, que
   la junta definió como obligatorio.
6. **WhatsApp**: existe el componente `SupportCard` con QR + botón,
   pero **no está montado en ninguna pantalla** y el env
   `NEXT_PUBLIC_WHATSAPP_SUPPORT_URL` no está configurado.

**Decisión final de readiness**:

> ✅ **READY ONLY IF P0 FIXES ARE COMPLETED**

Si el equipo despeja los P0 listados en `docs/P0_FIX_PLAN.md`
(8-10 horas de trabajo enfocado, ya scoped), la plataforma puede
recibir testers el lunes con la calidad que la junta exigió. Sin
esos arreglos, los testers se van a topar con etiquetas técnicas y
con el visor faltante del admin.

### Semáforo global

| Área                                | Estado      | Notas |
|-------------------------------------|-------------|-------|
| Auth + acceso por rol               | 🟢 Verde    | JWT + bcrypt + RBAC efectivo |
| Consent legal (pre-Entrar al espacio)| 🟢 Verde    | Gate operativo, versión `v0-draft` aún |
| Portal proveedor (dashboard/calendario/upload/notificaciones/submissions) | 🟢 Verde | Falla menor: badge enum crudo en wizard |
| Cliente (dashboard/vendors/submissions/notificaciones/calendar/activity/metadata) | 🟡 Amarillo | "Posible mismatch" inconsistente; calendar del cliente sin íconos clicables |
| Admin/Reviewer (decisión)           | 🟡 Amarillo | Decisión wired; faltó visor PDF embebido |
| Admin/Clients onboarding             | 🟡 Amarillo | Form admin existe; **falta email**; auto-seed manual |
| Renovaciones (CSF/REPSE/patronal)   | 🟢 Verde    | Cron diario en Render, notificaciones in-app idempotentes |
| Notificaciones in-app proveedor + cliente | 🟢 Verde | Semáforo wired |
| Notificaciones por email/WhatsApp   | 🔴 Rojo     | Sólo in-app; email/WA no implementados |
| Descargas (individual + ZIP por proveedor) | 🟢 Verde / 🟡 Amarillo | Provider y client tienen ZIP; admin NO tiene botón de ZIP |
| Reportes (provider/client)          | 🟢 Verde    | Phase 3.1 estable; AI generation Phase 3.3+ deferido |
| Bug reporting → Slack               | 🟢 Verde    | Capture, persistencia, Slack delivery, triaje admin |
| Multi-archivo (contrato + anexo)    | 🟡 Amarillo | Implementado, flag apagado |
| Sidebar plegable                    | 🟡 Amarillo | Hamburguesa móvil sí; sin modo "íconos" desktop |
| Perfil de usuario / dropdown estilo LinkedIn | 🔴 Rojo | No existe, solo botón "Cerrar sesión" |
| WhatsApp integración                | 🔴 Rojo     | Componente existe, no montado, sin URL |
| Búsqueda por tags/metadata          | 🟡 Amarillo | Cliente tiene búsqueda; sin API de tags |
| Filtros institucion + bulk download | 🟢 Verde    | Backend lista filtros; UI parcial |

### Top 10 hallazgos

1. **Etiquetas `posible_mismatch` inconsistentes** entre 5+ pantallas: "Posible mismatch" / "Posible discrepancia" / "Posible inconsistencia". P0.
2. **`<Badge>{result.status}</Badge>`** renderiza enum crudo en `intake-wizard.tsx:1736`. P0.
3. **Admin reviewer detail** muestra "Este documento ahora está en {new_status}" con enum crudo (`reviewer/[submission_id]/page.tsx:215`). P0.
4. **Sin visor PDF para el admin reviewer**: solo metadatos + signals. P0.
5. **Multi-archivo (contrato/anexo) detrás de flag apagado.** Habilitarlo el lunes o comunicar a testers que es de un solo archivo. P1.
6. **WhatsApp integración inexistente**, componente huérfano (`support-card.tsx` sin mount). P1.
7. **Form admin de alta de cliente sin campo email** (`admin/clients/page.tsx:252-291`). P0.
8. **No existe form/página para cliente nuevo post-pago** que la junta pidió. P1.
9. **Sin perfil de usuario / dropdown** estilo LinkedIn. P1.
10. **Cliente calendar** muestra agregados mensuales pero **no íconos por institución ni click-to-action**. P1.

---

## 2. Comandos ejecutados (Phase 2)

| Comando | Directorio | Resultado | Detalle |
|---|---|---|---|
| `npm run typecheck` | `apps/web` | ✅ pasa | tsc --noEmit sin errores |
| `npm run lint` | `apps/web` | ✅ pasa | ESLint limpio |
| `npm run check:print` | `apps/web` | ✅ pasa | Print contract OK |
| `npm run check:intents` | `apps/web` | ✅ pasa | 28 casos de Wise intent OK |
| `NEXT_PUBLIC_API_BASE_URL=… npm run build` | `apps/web` | ✅ pasa | 43 rutas estáticas/dinámicas; build verde |
| `python -m pytest tests -q` | `apps/api` | ✅ pasa | **922 tests pass**, 14 warnings, 132s |
| `python -m ruff check app` | `apps/api` | ⚠️ 13 issues | Sólo `app/services/wise/ai.py` y `app/services/wise/context.py` (line-length + 1 unused import). No bloquea. |

**No se ejecutó** ningún comando destructivo, ni alembic upgrade, ni
git push, ni rotaciones de secretos. La base de datos local
`apps/api/checkwise.db` no se modificó.

### Lint del backend (no bloquea)

13 issues de ruff aislados en dos archivos:

- `apps/api/app/services/wise/ai.py` — 9 violaciones E501 (líneas largas).
- `apps/api/app/services/wise/context.py` — 1× E501, 1× F401 (`field` no usado), 1× I001 (orden imports), 1× UP017 (`timezone.utc` vs `datetime.UTC`).

Recomendación: arreglar en un commit aparte la próxima semana; no
relacionado con Monday readiness.

---

## 3. Auditoría ruta por ruta (Phase 3)

### 3.1 Portal del proveedor

| Ruta | Estado | Halllazgos |
|------|--------|-----------|
| `/login` | 🟢 listo | Sanitización del `next` param + redirect por rol (`login/page.tsx:272`); rate limit en backend |
| `/activate` | 🟢 listo | Activación obliga cambio de password, bug `CW-AUD-P1-01` ya corregido (`activate/page.tsx:172`) |
| `/forgot-password` / `/reset-password` | 🟢 listo | Flujo email→token funcional |
| `/portal/entra-a-tu-espacio` | 🟢 listo | Legal consent gate bloquea submit (`page.tsx:382-385`); persiste antes del PATCH profile. **DRAFT visible**: la versión `v0-draft` aparece en las páginas legales y en frontmatter — comunicar a testers o intercambiar por copy aprobado. |
| `/portal/onboarding` | 🟢 listo | Sección "Opcionales" ya es `collapsible` (`onboarding/page.tsx:218-224`) |
| `/portal/dashboard` | 🟢 listo | Sin "tiempo de revisión", semáforo y contadores correctos |
| `/portal/calendar` | 🟢 listo | Íconos por institución (`calendar/page.tsx:58-63`), drawer clickable, deep-link prefilled (`drawerAction` en `calendar/page.tsx:839-895`) |
| `/portal/upload` | 🟡 con borde | `IntakeWizard` rinde `<Badge>{result.status}</Badge>` con enum crudo (línea 1736). Multi-file flag apagado por defecto. |
| `/portal/submissions` | 🟡 con borde | Sin dropdown de filtros (solo agrupación fija por institución/año/mes). Para Monday OK; mejora P1. |
| `/portal/submissions/[id]` | 🟢 listo | Visor PDF embebido (iframe + Blob URL) + botón "Descargar PDF" (`page.tsx:493-600`). Visible **antes** de re-subir. |
| `/portal/notifications` | 🟢 listo | Color por severidad (verde/yellow/red/info), `read_at`, deep links |
| `/portal/reports` / `[id]` / `[id]/print` | 🟢 listo | Preset por audiencia, vista de impresión validada por `check:print` |

### 3.2 Portal del cliente

| Ruta | Estado | Halllazgos |
|------|--------|-----------|
| `/client` | 🟢 redirige a `/client/dashboard` |
| `/client/dashboard` | 🟡 con borde | **Línea 519**: `posible_mismatch` etiquetada como **"Posible mismatch"** (inglés). Otras pantallas usan "Posible discrepancia" / "Posible inconsistencia". |
| `/client/submissions` | 🟢 listo | Filtros al top (Proveedor, Estado, Institución, Periodo) — exactamente como pidió la junta. Status mapeados a español. |
| `/client/vendors` | 🟢 listo | Vendor name + RFC + semáforo + filas de KPI por proveedor + dropdown filter |
| `/client/vendors/[id]` | 🟢 listo | Card hero + radial gauge + ZIP download (`page.tsx:84-96`) |
| `/client/calendar` | 🟡 amarillo | Vista agregada mensual SIN íconos por institución y SIN click-to-action. La junta pidió íconos + clickable. |
| `/client/notifications` | 🟢 listo | Semáforo aplicado (`page.tsx:42-83`), agrupación por día |
| `/client/activity` | 🟢 listo | Audit log paginable + íconos por tipo |
| `/client/metadata` | 🟢 listo | Búsqueda libre en proveedor/periodo/etiquetas/etc. + download XLSX |
| `/client/reports` / `[id]` | 🟢 listo | Wrapper de `ReportsListView` / `ReportEditor` |

### 3.3 Admin

| Ruta | Estado | Halllazgos |
|------|--------|-----------|
| `/admin` (home) | 🟢 listo | Redirect por rol (`internal_admin` vs `reviewer`) |
| `/admin/login` | 🟢 listo | |
| `/admin/dashboard` | 🟢 listo | **Sin** "heat indicator" ni SLA timer. Hero muestra "X documentos en cola humana" sin estimación de tiempo. |
| `/admin/reviewer` | 🟢 listo | Filtros por estado, badge "FIFO · más viejos primero", `age_hours` por fila. Sin filtro provider/client/period en UI (API sí lo soporta). |
| `/admin/reviewer/[id]` | 🔴 falta visor | Decisión (approve/reject/clarification/exception) + observaciones funciona. **NO hay preview del PDF**. La copy "Este documento ahora está en {new_status}" (línea 215) muestra el enum crudo. |
| `/admin/clients` | 🟡 con borde | Form de alta tiene Nombre/RFC/Responsable/Estado. **Falta el campo email** que pidió la junta. Status options en inglés ("active"/"inactive"). |
| `/admin/clients/[id]/metadata` | 🟢 listo | |
| `/admin/vendors` | 🟢 listo | |
| `/admin/calendar` | 🟢 listo | |
| `/admin/requirements` | 🟢 listo | |
| `/admin/audit-log` | 🟢 listo | |
| `/admin/contact-requests` | 🟢 listo | |
| `/admin/correction-requests` | 🟢 listo | |
| `/admin/feedback-reports` | 🟢 listo | Triage queue completo (status, resolution_note, Slack delivery status) |
| `/admin/metadata` | 🟢 listo | |
| `/admin/reports` / `[id]` | 🟢 listo | |

### 3.4 Legal

| Ruta | Estado | Halllazgos |
|------|--------|-----------|
| `/legal/privacidad` | 🟡 borrador | `version="v0-draft"` (`legal/privacidad/page.tsx:27`). Pendiente firma Paco/Beko. |
| `/legal/terminos` | 🟡 borrador | `version="v0-draft"` (`legal/terminos/page.tsx:28`). |
| `/legal/consentimiento` | 🟡 borrador | `version="v0-draft"` (`legal/consentimiento/page.tsx:28`). |

Los tres expoenen el draft. La junta dijo que el texto de Términos
y Condiciones existe en JotForms y debe migrar al sitio. **Esa
migración aún no se hizo.**

### 3.5 Otras

- `/dev/calendar-preview` — herramienta interna de testing; no afecta a usuarios reales.
- `/` (landing) — público, `FeedbackLauncher allowPublic` activado.

---

## 4. Auditoría de datos y backend (Phase 5)

| Área | Soporte | Evidencia |
|------|---------|-----------|
| Clientes / Proveedores / Periodos / Instituciones / Requerimientos / Submissions / Documents / Validations / DocumentInspection / DocumentStatusHistory | ✅ completo | `apps/api/app/models/entities.py:42-348` |
| ProviderWorkspace (tenancy proveedor) + tokens de acceso | ✅ | `entities.py:350-400` (token único + `legal_consent_accepted_at` + `profile_confirmed_at`) |
| Organizations + Users + Memberships + PasswordResetToken | ✅ | `entities.py:403-524` |
| AuditLog | ✅ escribe; queryable desde admin | `entities.py:526-540` + `services/audit_log.py` |
| Reports + ReportVersion + ReportConversation + ComplianceSnapshot + ReportShare + ReportExport | ✅ CRUD listo, AI Phase 3.3+ deferido | `entities.py:552-756` |
| ContactRequest (landing) | ✅ | `entities.py:759-790` |
| FeedbackReport (bug reports) | ✅ Slack delivery + triage | `entities.py:791-888` |
| WiseEvent (analytics) | ✅ | `entities.py:890-921` |
| ProviderNotification | ✅ con severidad | `entities.py:924-958` |
| ClientNotification | ✅ con semáforo | `entities.py:961-993` |
| RenewalReminder (idempotencia por ciclo) | ✅ | `entities.py:998-1041` |

**Cobertura**: la base de datos soporta todos los conceptos que la
junta pidió. Los huecos son **superficies UI** (admin sin visor,
WhatsApp sin integración) y **transportes** (email/WhatsApp aún no
salen del sistema).

---

## 5. Validación de documentos (Phase 6)

`apps/api/app/services/document_intelligence.py` y
`prevalidation.py` saben:

- ✅ Qué documento se espera para un requirement code (`_expected_document_type`).
- ✅ Quién lo subió (workspace_id), para qué provider, contrato, periodo, institución, requerimiento (todo en `Submission`).
- ✅ Detecta mismatch_reason y produce `anomaly_codes`: `possible_document_type_mismatch`, `possible_institution_mismatch`, `period_not_confirmed`.
- ✅ La razón se guarda en `ValidationEvent` con `context_message` y se enseña al proveedor en `/portal/submissions/[id]` y el hero del intake wizard.
- ✅ El documento original sigue visible en la pantalla de detalle, **antes** de que el proveedor suba uno nuevo (visor PDF embebido + botón descargar).
- 🟡 Multi-archivo: **flag apagado**. Hay endpoint `finalize_multi_document_submission` y tests, pero no está expuesto en producción.
- 🟡 Anexo separado: actualmente el wizard tiene un input "Archivos adicionales (anexos)" cuando `multiFileEnabled === true`; un único input para anexos, **sin distinción semántica entre contrato y anexo a nivel de modelo**.

**Recomendación**: para Monday dejar el flag apagado; comunicar a
testers que la carga es de un archivo a la vez. Activar después.

---

## 6. Notificaciones (Phase 7)

| Capacidad | Estado |
|-----------|--------|
| Modelo de notificación proveedor + cliente | ✅ con `severity` |
| UI proveedor `/portal/notifications` | ✅ semáforo + read state + deep links |
| UI cliente `/client/notifications` | ✅ semáforo + read state + agrupación día |
| Trigger reviewer decision → provider notification | ✅ `services/submission_workflow.py:319` invoca `notify_provider_of_reviewer_decision` |
| Trigger provider upload → client notification | ✅ `services/client_notifications.py:58-90` (`notify_provider_uploaded`) |
| Cron renovaciones (CSF 90d / REPSE 1095d / patronal 1095d) | ✅ `render.yaml:170-189` (`0 14 * * *`) → `services/renewal_dispatch.py` |
| Severidad de renovación (verde/yellow/red) | ✅ `renewal_dispatch.py:66-68` |
| Email outbound | 🔴 no existe (sí hay `services/email_delivery.py` para password reset, pero no para renovaciones ni decisiones) |
| WhatsApp outbound | 🔴 no existe |
| Porcentaje de completitud en notificación al cliente | 🟡 datos disponibles, no embebidos en el mensaje |

---

## 7. Calendario (Phase 8)

| Capacidad | Portal | Cliente |
|-----------|--------|---------|
| Lista de pendientes | ✅ | ✅ (agregado mensual) |
| Íconos por institución | ✅ | ❌ |
| Clickable / drill-down | ✅ (drawer) | ❌ (sólo tabla) |
| Deep-link a `/portal/upload` con prefill | ✅ | n/a |
| Mobile-first | ✅ | ✅ |
| Drawer con "Acerca de este comprobante" + acción | ✅ `calendar/page.tsx:815-832` | ❌ |

El cliente NO recibe la misma experiencia clicable que el proveedor.

---

## 8. Admin (Phase 9)

| Capacidad | Estado |
|-----------|--------|
| Ver pendientes | ✅ `/admin/reviewer` |
| Abrir/ver doc subido | ❌ no hay embed PDF; solo metadatos |
| Aprobar / Rechazar / Aclarar / Excepción | ✅ `review-decision-panel.tsx:157-258` |
| Comentarios / observaciones al proveedor | ✅ textarea `observations` separada de `reason` |
| Filtros provider/client/inst/periodo/status | 🟡 status + institución en UI; provider/client visibles como columnas; periodo sólo por queryparam |
| Gating de acceso (Isaac/Paco/dev only) | ✅ `MembershipRole.INTERNAL_ADMIN` enforcement en `apps/api/app/api/v1/admin.py:76-80` |
| Reviewer gate (más permisivo) | ✅ `require_any_role(REVIEWER, INTERNAL_ADMIN)` en `reviewer.py:46-49` |
| Form alta de cliente | 🟡 manual; falta email |
| Bulk ZIP por proveedor desde admin | ❌ endpoint sólo lado provider (`portal.py`). Admin no tiene botón. |

---

## 9. Descargas (Phase 10)

| Capacidad | Backend | UI proveedor | UI cliente | UI admin |
|-----------|---------|--------------|------------|----------|
| Descarga individual | ✅ `submissionDownloadUrl` con `?download=1` | ✅ botón "Descargar PDF" | 🟡 indirecto (vía ZIP) | ❌ |
| ZIP por proveedor | ✅ `services/expediente_zip.py` (200 archivos, 500 MB) | ✅ desde calendario | ✅ desde `/client/vendors/[id]` (`page.tsx:84`) | ❌ |
| Filtros (period_key / institution / status) | ✅ `ExpedienteFilters` | parcial | parcial | n/a |
| Control de acceso por tenant | ✅ guard en dependencias | ✅ | ✅ | n/a |
| Audit row `provider.document_downloaded` | ✅ se escribe | n/a | n/a | n/a |

---

## 10. Bug reporting / Slack (Phase 11)

| Capacidad | Estado |
|-----------|--------|
| Lanzador flotante en portal/client/admin/landing | ✅ `feedback-launcher.tsx` montado en 5 lugares |
| Captura de pantalla con `html2canvas` (excluye launcher) | ✅ `feedback-launcher.tsx:215-260` |
| Permitir adjuntar imagen manual (PNG, 5 MB cap) | ✅ |
| Capturar `url`, `path`, `viewport`, `user_agent`, console logs | ✅ |
| Reporte autenticado vs público | ✅ `POST /api/v1/feedback` vs `/feedback/public` |
| Persistencia en `feedback_reports` | ✅ |
| Slack delivery vía `BackgroundTask` (nunca bloquea) | ✅ `feedback_service.py:12+` |
| Reporter name + roles en payload | ✅ `user_full_name` + `user_roles` denormalizados |
| Rate limit | ✅ 10/min autenticado, 5/hora público |
| Triage UI `/admin/feedback-reports` | ✅ status transitions + resolution_note + estado de Slack |
| Reintento manual de envío a Slack | ❌ no existe botón |
| AI triage automático | ❌ Phase 2+, fuera de alcance |

---

## 11. Mapa de riesgos para Monday

### P0 (pueden confundir al tester o bloquear el flujo)

1. **Etiqueta `posible_mismatch` inconsistente** entre pantallas — usar copy único.
2. **`<Badge>{result.status}</Badge>`** en `intake-wizard.tsx:1736` muestra enum crudo.
3. **"Este documento ahora está en {new_status}"** en `admin/reviewer/[submission_id]/page.tsx:215` muestra enum crudo.
4. **Form admin de alta de cliente sin campo email** — la junta lo señaló como dato mínimo.
5. **Admin reviewer sin visor PDF embebido** — Isaac/Paco no podrán ver el archivo desde la pantalla de decisión.

### P1 (importantes, no bloquean lunes)

6. **WhatsApp integración**: montar `SupportCard` o un widget, definir `NEXT_PUBLIC_WHATSAPP_SUPPORT_URL`.
7. **Página/form de auto-registro de cliente post-pago** (la junta lo pidió).
8. **Cliente calendar**: añadir íconos por institución y drill-down clicable.
9. **Sidebar plegable estilo "íconos"** en desktop (móvil ya colapsa).
10. **Dropdown de perfil de usuario** estilo LinkedIn (hoy solo hay logout).
11. **Multi-archivo (contrato + anexo)**: o se enciende con feature flag y se prueba, o se comunica que está apagado.

### P2 (arquitectura futura, no para Monday)

12. AI bug triage (Phase 2+ del plan).
13. WhatsApp transactional (renovaciones, decisiones).
14. Email transactional para renovaciones/decisiones.
15. Búsqueda full-text por tags/metadata (API).
16. Bulk ZIP desde la superficie admin.
17. Anexos como entidad separada en el modelo (vs sólo "archivos adicionales").

---

## 12. Lo que NO se pudo verificar

- **NO VERIFICADO**: si los testers del lunes ya tienen cuenta sembrada y si Paco/Beko firmaron los textos de `legal/*`. Evidencia faltante: lista de testers + revisión legal de los drafts `v0-draft`.
- **NO VERIFICADO**: si el Slack token configurado en Render alcanza para el canal `#checkwise-feedback` (no se hicieron llamadas live a la API de Slack durante la auditoría).
- **NO VERIFICADO**: comportamiento real de `playwright` para report exports en el cron de Render (no se corrió la rama de export en este audit).
- **NO VERIFICADO**: si el cron `checkwise-renewal-dispatch` está actualmente activo en Render (el blueprint está sincronizado, pero la confirmación de "última corrida exitosa" requiere consola de Render).
- **NO VERIFICADO**: la integración real con los almacenes R2/S3 (los tests usan moto/in-memory).

---

## 13. Conclusión

El sistema tiene un núcleo muy sólido: modelo de datos completo,
tests verdes, build limpio, separación de roles real, semáforo,
notificaciones, renovaciones, downloads y bug reporting funcionales.

Los puntos que separan a CheckWise de "listo para Monday" son
de **UX y pulido**, no de arquitectura. El plan en
`docs/P0_FIX_PLAN.md` lista la secuencia tactica para llegar a verde
en una sesión de 8-10 horas.

Documentos relacionados producidos por esta auditoría:

- `docs/FRIDAY_MEETING_ACTION_MATRIX.md` — matriz de acción item-por-item.
- `docs/P0_FIX_PLAN.md` — plan táctico Monday-blocker.
- `docs/FUTURE_SYSTEMS_ARCHITECTURE_NOTES.md` — arquitectura a futuro.
- `docs/UX_COPY_RECOMMENDATIONS.md` — recomendaciones de copy en español.
