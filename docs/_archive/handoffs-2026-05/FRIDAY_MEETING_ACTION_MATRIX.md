# Matriz de acción — Junta del viernes 2026-05-23

Una fila por cada ítem accionable de la junta. Cada uno tiene
estado verificado contra código, evidencia (archivo:línea), riesgo,
prioridad, complejidad, fix recomendado y criterio de aceptación.

Leyenda:
- **DONE** = verificable en código.
- **PARTIAL** = parcialmente entregado, falta algo nombrado.
- **MISSING** = no existe.
- **BROKEN** = existe pero rompe la UX.
- **NEEDS DESIGN** = decisión de producto pendiente.
- **NO VERIFICADO** = no se pudo confirmar sin evidencia externa.

---

## Action items

### 1. Consentimiento y aviso de privacidad/términos antes de "Entrar a tu espacio"
- **Usuario**: proveedor
- **Estado**: DONE
- **Evidencia**: [`apps/web/app/portal/entra-a-tu-espacio/page.tsx:78-89`](apps/web/app/portal/entra-a-tu-espacio/page.tsx) + `LegalConsentBlock` (línea 635-700+); el botón "Entrar a mi espacio" está deshabilitado mientras `needsLegalConsent && !legalConsentAccepted` (`page.tsx:382-385`); persiste consent vía `acceptLegalConsent()` antes del PATCH profile.
- **Riesgo**: bajo. La versión es `v0-draft` y todavía no está firmada por Paco/Beko.
- **Prioridad**: P1 (legal review)
- **Complejidad**: small (intercambiar copy aprobado)
- **Fix**: cuando llegue copy aprobado, bumpear `current_legal_consent_version` en el backend y actualizar los `<LegalDocumentPage version="v0-draft">` en `apps/web/app/legal/*/page.tsx`.
- **Aceptación**: la versión renderizada deja de decir "DRAFT" y los users existentes son re-promptados (el flujo de versionado ya está en su lugar).

---

### 2. Textos de Términos y Condiciones desde JotForms
- **Usuario**: cliente / proveedor
- **Estado**: PARTIAL
- **Evidencia**: `apps/web/app/legal/terminos/page.tsx` existe pero sigue como `v0-draft`. El JotForms upstream no fue migrado.
- **Riesgo**: medio. Si el lunes alguien lee los términos, va a ver un borrador con disclaimer.
- **Prioridad**: P1
- **Complejidad**: small-medium (copy ops)
- **Fix**: pasar el HTML/text de los términos de JotForms al `LegalDocumentPage` correspondiente.
- **Aceptación**: las tres páginas legales muestran texto firmado, sin el badge de DRAFT.

---

### 3. Form/página para cliente post-pago (alta inicial)
- **Usuario**: cliente
- **Estado**: MISSING (en cliente). PARTIAL (en admin).
- **Evidencia**: no existe `/client/onboarding` ni `/client/alta`. El admin tiene un form en [`apps/web/app/admin/clients/page.tsx:209-303`](apps/web/app/admin/clients/page.tsx) con Nombre/RFC/Responsable/Estado. **Falta el campo email** que la junta marcó como obligatorio.
- **Riesgo**: alto. La junta dijo "Only basic client information is required at payment time: RFC, email, name." Hoy no hay un canal de entrada self-service para el cliente.
- **Prioridad**: P1 (P0 si los testers del lunes son clientes nuevos que vienen del flujo de pago)
- **Complejidad**: medium
- **Fix sugerido**:
  1. Añadir campo `email` al `ClientForm` admin (`apps/web/app/admin/clients/page.tsx`) y al schema backend (`apps/api/app/schemas/...ClientCreate`).
  2. Crear ruta pública/protegida-por-token `/client/onboarding` que tome RFC, email, nombre y dispare `POST /api/v1/admin/clients` (con un token de invitación o con un endpoint público distinto).
- **Aceptación**: cliente nuevo entra a `/client/onboarding`, llena RFC + email + nombre, recibe email de bienvenida, queda creado.

---

### 4. Integrar número de WhatsApp
- **Usuario**: proveedor, cliente
- **Estado**: MISSING (componente existe, no montado, sin env)
- **Evidencia**: [`apps/web/components/checkwise/support-card.tsx`](apps/web/components/checkwise/support-card.tsx) — componente listo, pero `grep -rn SupportCard apps/web` solo devuelve la propia definición; no está montado. Env `NEXT_PUBLIC_WHATSAPP_SUPPORT_URL` no está definido en `apps/web/.env.local` ni en `render.yaml`.
- **Riesgo**: medio.
- **Prioridad**: P1
- **Complejidad**: small
- **Fix**:
  1. Montar `<SupportCard />` en el sidebar del portal y/o como botón en la nav (proveedor y cliente).
  2. Configurar `NEXT_PUBLIC_WHATSAPP_SUPPORT_URL=https://wa.me/52XXXXXXXXXX` en Render.
  3. Opcional: añadir `NEXT_PUBLIC_SUPPORT_QR_PLACEHOLDER_URL` con un QR real.
- **Aceptación**: el botón "Abrir soporte" aparece y abre WhatsApp en una pestaña nueva.

---

### 5. Notificaciones de renovación cada 3 meses (constancia de situación fiscal)
- **Usuario**: proveedor, cliente
- **Estado**: DONE
- **Evidencia**: [`apps/api/app/services/renewal_dispatch.py:306`](apps/api/app/services/renewal_dispatch.py) — CSF renueva a 90 días. Thresholds en [`renewal_dispatch.py:66-68`]. Cron diario en [`render.yaml:170-189`].
- **Riesgo**: bajo.
- **Prioridad**: —
- **Aceptación**: la primera notificación amarilla aparece cuando faltan 30 días.

---

### 6. Notificaciones de renovación cada 3 años (REPSE)
- **Usuario**: proveedor, cliente
- **Estado**: DONE
- **Evidencia**: [`apps/api/app/services/renewal_dispatch.py:385`](apps/api/app/services/renewal_dispatch.py) — REPSE a 1095 días.
- **Riesgo**: bajo.
- **Prioridad**: —

---

### 7. Rediseño de sección "documentos opcionales"
- **Usuario**: proveedor
- **Estado**: DONE (collapsible)
- **Evidencia**: [`apps/web/app/portal/onboarding/page.tsx:217-235`](apps/web/app/portal/onboarding/page.tsx) — sección "Opcionales — puedes hacerlos después" con prop `collapsible` y tono `info`.
- **Riesgo**: bajo.
- **Prioridad**: —
- **Aceptación**: ya se ve como bar colapsable.

---

### 8. Eliminar indicador de tiempo / heat de revisión en el admin dashboard
- **Usuario**: admin
- **Estado**: DONE en el dashboard.
- **Evidencia**: [`apps/web/app/admin/dashboard/page.tsx:85-167`](apps/web/app/admin/dashboard/page.tsx) — hero muestra solo conteo y narrativa, sin estimaciones de SLA ni heat. El reviewer queue sí muestra `age_hours` por fila ([`admin/reviewer/page.tsx:264`]) que es un dato distinto (antigüedad real, no estimación).
- **Riesgo**: bajo.
- **Prioridad**: —
- **Sugerencia**: si la junta quiso eliminar también el `age_hours` por fila, retirarlo de la columna de reviewer. Confirmar con Paco/Beko.

---

### 9. Notificaciones al proveedor por aprobación/rechazo
- **Usuario**: proveedor
- **Estado**: DONE (in-app)
- **Evidencia**: [`apps/api/app/services/provider_notifications.py:96-99`](apps/api/app/services/provider_notifications.py) — invoca en `submission_workflow.py:319` cuando el reviewer decide. UI: `/portal/notifications`.
- **Riesgo**: bajo.
- **Email/WhatsApp**: aún no, ver ítem 17 abajo.
- **Aceptación**: ya operativo.

---

### 10. Notificaciones al cliente sobre estado de carga de sus proveedores
- **Usuario**: cliente
- **Estado**: DONE (in-app)
- **Evidencia**: [`apps/api/app/services/client_notifications.py:58-90`](apps/api/app/services/client_notifications.py) — `notify_provider_uploaded`. UI: `/client/notifications`.
- **Falta**: % de completitud en el cuerpo de la notificación (se podría calcular ya desde los datos).
- **Prioridad**: P2
- **Complejidad**: small

---

### 11. Semáforo (verde/yellow/red) en notification center
- **Usuario**: proveedor + cliente
- **Estado**: DONE
- **Evidencia**: `severity` en `ClientNotification` y `ProviderNotification` con valores `green|yellow|red|info`. UI: [`apps/web/app/client/notifications/page.tsx:42-83`](apps/web/app/client/notifications/page.tsx) y [`apps/web/app/portal/notifications/page.tsx:40-81`](apps/web/app/portal/notifications/page.tsx).
- **Riesgo**: bajo.

---

### 12. Botones de navegación atrás/adelante o paths de regreso claros
- **Usuario**: todos
- **Estado**: PARTIAL
- **Evidencia**: la mayoría de las rutas tiene "Volver" o crumbs (`/client/vendors/[id]:98-101`, `/portal/submissions/[id]`, `/admin/reviewer/[id]`). Algunas pantallas detalle no tienen breadcrumb completo; navegación entre módulos depende del sidebar.
- **Prioridad**: P1
- **Complejidad**: medium (sistemático)
- **Fix**: introducir un componente `PageHeader` con breadcrumbs en todas las rutas detail.

---

### 13. Rework /submissions con dropdown de proveedor y lenguaje natural
- **Usuario**: proveedor + cliente
- **Estado**: DONE en cliente; PARTIAL en proveedor
- **Evidencia cliente**: [`apps/web/app/client/submissions/page.tsx:137-203`](apps/web/app/client/submissions/page.tsx) — filtros Proveedor/Estado/Institución/Periodo arriba, lenguaje en español.
- **Evidencia proveedor**: [`apps/web/app/portal/submissions/page.tsx`](apps/web/app/portal/submissions/page.tsx) agrupa por institución/año/mes sin dropdown de filtros.
- **Prioridad**: P1
- **Complejidad**: small (replicar patrón del cliente)

---

### 14. Filtros de búsqueda por institución
- **Usuario**: cliente
- **Estado**: DONE
- **Evidencia**: `INSTITUTION_LABELS` y dropdown en `/client/submissions/page.tsx` y `/client/vendors/page.tsx`.

---

### 15. Búsqueda por tags/metadata
- **Usuario**: cliente
- **Estado**: PARTIAL
- **Evidencia**: [`apps/web/app/client/metadata/page.tsx:45-62`](apps/web/app/client/metadata/page.tsx) — búsqueda full-text local sobre XLSX preview. **No hay API de búsqueda server-side**.
- **Prioridad**: P2
- **Complejidad**: medium-large
- **Fix futuro**: endpoint `GET /api/v1/metadata/search?q=` que indexe `client_metadata` (ver `services/client_metadata.py`).

---

### 16. Reemplazar Vendor ID con nombre del proveedor
- **Usuario**: cliente, proveedor, admin
- **Estado**: DONE
- **Evidencia**: `grep -rn "Vendor ID" apps/web` devuelve cero matches en UI. Todas las superficies usan `vendor_name`. `vendor_id` se usa sólo como key/ruta.

---

### 17. Descarga individual + ZIP bulk por proveedor
- **Usuario**: cliente, proveedor
- **Estado**: DONE (provider + cliente). MISSING (admin).
- **Evidencia individual**: [`apps/web/app/portal/submissions/[submission_id]/page.tsx:551-575`](apps/web/app/portal/submissions/[submission_id]/page.tsx) — botón "Descargar PDF" con audit row `provider.document_downloaded`.
- **Evidencia ZIP**: [`apps/api/app/services/expediente_zip.py`](apps/api/app/services/expediente_zip.py) — cap 200 archivos / 500 MB; folder layout `<institution>/<period_key>/<filename>`; UI en `/client/vendors/[id]:84-96`.
- **Falta**: botón "Descargar ZIP del proveedor" en `/admin/vendors/[id]` o `/admin/clients/[id]` (no existe).
- **Prioridad**: P1
- **Complejidad**: small (reusar endpoint)

---

### 18. Filtros de descarga por periodo / institución / tipo de documento
- **Usuario**: cliente
- **Estado**: PARTIAL
- **Evidencia**: backend soporta `?status=&period_key=&institution=` ([`services/expediente_zip.py`](apps/api/app/services/expediente_zip.py) `ExpedienteFilters`). UI cliente no expone los tres en un panel de filtros; sólo expone descarga global.
- **Prioridad**: P2
- **Complejidad**: small

---

### 19. Notificaciones de renovación por email y WhatsApp
- **Usuario**: proveedor + cliente
- **Estado**: MISSING
- **Evidencia**: actualmente sólo se crean rows en `client_notifications` / `provider_notifications`. No hay `services/whatsapp_delivery.py`; `email_delivery.py` solo se usa para password reset.
- **Prioridad**: P2
- **Complejidad**: medium-large
- **Fix futuro**: ver `docs/FUTURE_SYSTEMS_ARCHITECTURE_NOTES.md` § "Email/WhatsApp delivery".

---

### 20. Calendario con íconos por institución y clickable
- **Usuario**: cliente, proveedor
- **Estado**: PARTIAL
- **Evidencia portal**: [`apps/web/app/portal/calendar/page.tsx:58-63`](apps/web/app/portal/calendar/page.tsx) — íconos + drawer + deep-link → DONE.
- **Evidencia cliente**: [`apps/web/app/client/calendar/page.tsx`](apps/web/app/client/calendar/page.tsx) — tabla agregada, **sin** íconos por institución y **sin** drill-down al detalle.
- **Prioridad**: P1
- **Complejidad**: medium (replicar patrón portal o nuevo diseño "panorámica del cliente")

---

### 21. Sidebar plegable
- **Usuario**: todos
- **Estado**: PARTIAL
- **Evidencia**: en desktop el sidebar es fijo (`portal-app-shell.tsx:159-235`). En mobile colapsa en hamburguesa.
- **Prioridad**: P1
- **Complejidad**: medium
- **Fix**: añadir botón "Colapsar/Expandir" y modo "íconos" para `lg+`.

---

### 22. Sección de perfil de usuario
- **Usuario**: todos
- **Estado**: MISSING
- **Evidencia**: solo botón "Cerrar sesión" en los tres shells. No hay dropdown de perfil estilo LinkedIn ni página `/perfil`.
- **Prioridad**: P1
- **Complejidad**: medium
- **Fix**: añadir `UserMenuDropdown` con (Mi perfil, Preferencias, Soporte WhatsApp, Cerrar sesión). El backend ya soporta `phone`, `job_title`, `contact_preference` en `User`.

---

### 23. Paco: enviar video del error de cuenta pendiente
- **Estado**: NO VERIFICADO (acción externa, no de código)
- **Prioridad**: —

---

### 24. Trabajar en la página de admin
- **Usuario**: admin
- **Estado**: PARTIAL — la página existe pero le faltan capas (visor PDF, ZIP por vendor, filtros completos en UI, alta de cliente con email). Ver MONDAY_READINESS_AUDIT.md §3.3.
- **Prioridad**: P0 (visor PDF) + P1 (resto)
- **Complejidad**: medium

---

## Bloques temáticos adicionales de la junta

### Onboarding del cliente (admin pre-loads)
- **Estado**: PARTIAL — el form de alta admin existe, pero le falta el campo email. No hay auto-seed desde Slack/pago. Ver ítem 3.

### Revisión y visualización de documentos
- **Estado**: DONE para proveedor (visor inline + descargar PDF). MISSING para admin reviewer.
- **Razón de rechazo más clara**: DONE. El reviewer captura razón + observaciones; provider la ve en `/portal/submissions/[id]` (`page.tsx:325-345`).
- **Sin "señales de calidad" vagas**: DONE. El copy actual usa "prevalidaciones automáticas iniciales" y razones específicas.

### Reportes de bugs
- Estado actual: DONE. Slack + screenshot + reporter name + persistencia + triage admin.
- AI triage: P2, no implementado.

### Validación AI de documentos
- ¿Sabe qué documento espera? DONE (`document_intelligence.py:_expected_document_type`).
- ¿Compara contra el requerimiento? DONE.
- ¿Detección de mismatch clara? DONE (`mismatch_reason` + `anomaly_codes` + UI).
- ¿Flujo de rechazo/corrección entendible? PARTIAL — funciona, pero la inconsistencia de etiquetas `posible_mismatch` enturbia el mensaje.

### Contratos y anexos
- Estado: PARTIAL. Multi-archivo existe en código (`MULTI_FILE_UPLOAD_ENABLED=False`). Anexo no es entidad separada en el modelo; es "archivo adicional" en la misma submission. Ver §5 del audit.

### Documentos de renovación periódica
- CSF cada 3 meses: DONE.
- REPSE cada 3 años: DONE.
- Registro patronal: DONE (mismo periodo que REPSE).

### Dashboard y visualización de estado
- Sin estimaciones de tiempo: DONE en admin dashboard.
- Contadores útiles (pendiente / en revisión / aprobado / rechazado): DONE en `AdminHero` y `MetadataStrip`.

### Metadata y tags
- Extracción automática: DONE (`prevalidation.py`, `document_intelligence.py`).
- Tags en search: PARTIAL — search local, no API.
- "Fecha principal" en docs con múltiples fechas: NEEDS DESIGN. Ver
  `FUTURE_SYSTEMS_ARCHITECTURE_NOTES.md` § "Metadata/tags".

### UX
- Diseño para 40-50 años: PARTIAL — copy y semáforo correctos; faltan
  affordances (perfil, atrás/adelante consistentes).
- Mobile + desktop: DONE (responsivo verificado).
- Sidebar plegable: PARTIAL.
- Profile dropdown LinkedIn: MISSING.
- Back/forward: PARTIAL (en las rutas principales sí, falta sistemática).
- Páginas "portfolio" sin whitespace excesivo: NEEDS DESIGN — depende de revisión visual con Paco/Beko.
