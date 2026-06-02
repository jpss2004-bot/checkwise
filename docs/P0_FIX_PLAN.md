# Plan táctico Monday — Fixes P0

> Trabajo enfocado para llegar de "ready if P0 fixes are completed"
> a "ready for testers reales". Estimado: 8-10 horas con un sólo
> desarrollador. Cada bloque tiene archivos exactos, criterio de
> aceptación y comando de verificación.

Orden de ejecución sugerido — empezar por los que tocan más usuarios
(las etiquetas) y terminar con los que requieren más pensamiento (el
visor PDF y el campo email).

---

## P0-1 · Unificar etiqueta `posible_mismatch` en toda la UI

**Por qué bloquea**: tres pantallas dicen tres cosas distintas
("Posible mismatch", "Posible discrepancia", "Posible inconsistencia")
para el mismo estado. La junta pidió evitar mezclas inglés–español
en UI no técnica.

**Decisión recomendada**: usar **"Posible inconsistencia"** en todas
las pantallas (es el que aparece en el badge canónico del portal:
`apps/web/components/checkwise/portal/requirement-status-badge.tsx:9`).

**Archivos a tocar**:

1. [`apps/web/app/client/dashboard/page.tsx:519`](apps/web/app/client/dashboard/page.tsx) — cambiar `"Posible mismatch"` → `"Posible inconsistencia"`.
2. [`apps/web/app/client/submissions/page.tsx:36`](apps/web/app/client/submissions/page.tsx) — cambiar `"Posible discrepancia"` → `"Posible inconsistencia"`.
3. [`apps/web/app/portal/submissions/[submission_id]/page.tsx:339`](apps/web/app/portal/submissions/[submission_id]/page.tsx) — cambiar `"Posible discrepancia"` → `"Posible inconsistencia"` (alineado con `STATUS_HEADLINE` que dice "podría no coincidir").
4. [`apps/web/app/admin/reviewer/page.tsx:52`](apps/web/app/admin/reviewer/page.tsx) — cambiar `"Posible mismatch"` → `"Posible inconsistencia"`.
5. [`apps/web/app/admin/reviewer/[submission_id]/page.tsx:349`](apps/web/app/admin/reviewer/[submission_id]/page.tsx) — cambiar `title="Posible mismatch"` → `title="Posible inconsistencia"`.
6. [`apps/web/components/checkwise/reports/blocks/attention-list.tsx:97-98`](apps/web/components/checkwise/reports/blocks/attention-list.tsx) — cambiar tanto `label` como `print` a `"Posible inconsistencia"`.
7. [`apps/web/components/checkwise/reports/blocks/upcoming-deadlines.tsx:104`](apps/web/components/checkwise/reports/blocks/upcoming-deadlines.tsx) — cambiar `"Posible mismatch"` → `"Posible inconsistencia"`.

**Aceptación**:

- `grep -rn "Posible mismatch" apps/web` devuelve cero matches.
- `grep -rn "Posible discrepancia" apps/web` devuelve cero matches.
- `npm run typecheck && npm run lint && npm run check:print` siguen verdes.

**Verificación**: `cd apps/web && npm run typecheck && npm run lint && npm run check:print`.

**Tiempo**: 30 min.

---

## P0-2 · Sustituir `<Badge>{result.status}</Badge>` en el intake wizard

**Por qué bloquea**: al terminar la carga el proveedor ve una etiqueta
literal `pendiente_revision` o `posible_mismatch` directo del enum.

**Archivo**: [`apps/web/components/checkwise/intake-wizard.tsx:1736`](apps/web/components/checkwise/intake-wizard.tsx).

**Fix**: reemplazar `<Badge>{result.status}</Badge>` por
`<RequirementStatusBadge status={result.status} />` (ese componente ya
existe en `apps/web/components/checkwise/portal/requirement-status-badge.tsx`
y traduce los enums a español natural).

**Aceptación**:

- En el flujo `/portal/upload`, al confirmar la carga, el badge dice
  "En revisión humana" o "Posible inconsistencia" (no `pendiente_revision`).
- Typecheck + lint verdes.

**Verificación**: `npm run typecheck && npm run lint && npm run build`.

**Tiempo**: 20 min.

---

## P0-3 · Sustituir `{decided.new_status}` crudo en admin reviewer

**Por qué bloquea**: el copy "Este documento ahora está en
{new_status}" rinde literal el enum y rompe la gramática española.

**Archivo**: [`apps/web/app/admin/reviewer/[submission_id]/page.tsx:212-218`](apps/web/app/admin/reviewer/[submission_id]/page.tsx).

**Fix**: introducir un mapa local o usar el `STATUS_LABELS_ES` del
backend (espejarlo en frontend si hace falta). Render sugerido:

```tsx
<p className="text-sm ...">
  Decisión registrada · ahora en estado{" "}
  <RequirementStatusBadge status={decided.new_status} />.
  La línea de tiempo refleja tu decisión.
</p>
```

**Aceptación**:

- El reviewer, después de aprobar, lee "Decisión registrada · ahora en
  estado **Aprobado**" (no "en aprobado").
- Typecheck + lint verdes.

**Tiempo**: 20 min.

---

## P0-4 · Añadir campo `email` al form admin de alta de cliente

**Por qué bloquea**: la junta lo definió como uno de los **tres**
datos mínimos del cliente al pagar.

**Archivos**:

1. **Frontend** — [`apps/web/app/admin/clients/page.tsx:209-303`](apps/web/app/admin/clients/page.tsx):
   - Añadir state `const [email, setEmail] = useState(...)`.
   - Añadir `<Field label="Correo" ...>` después del RFC.
   - Incluir `email` en el objeto pasado a `onSubmit`.
   - Marcar como `required type="email"`.

2. **API client** — [`apps/web/lib/api/admin.ts`](apps/web/lib/api/admin.ts):
   - Añadir `email?: string | null` al tipo `AdminClient` y al payload de `createClient`.

3. **Backend** — el schema `ClientCreate` en `apps/api/app/schemas/...` (buscar):
   - Añadir `email: EmailStr | None = None`.
   - Persistir en `Client.email` (o si no existe la columna aún, añadir
     migración Alembic — ver más abajo).

4. **DB**: verificar si el modelo `Client` ya tiene `email`. Si no,
   crear migración Alembic:
   ```bash
   cd apps/api
   ./.venv/bin/python -m alembic revision -m "add email to clients" --autogenerate
   ```
   y revisar el archivo generado.

**Aceptación**:

- El form admin tiene cuatro campos: Nombre, RFC, Correo, Responsable.
- Crear un cliente con email lo guarda en DB.
- 922 tests siguen pasando + un nuevo test que verifica email se
  persiste.

**Tiempo**: 1.5 h (incluye migración + test).

> Si el viernes hay urgencia y este P0 se vuelve P1 por el riesgo de
> migración, dejar email como un campo de texto plano sin validación
> de email-format y posponer la migración a una sesión separada.

---

## P0-5 · Añadir visor PDF al admin reviewer

**Por qué bloquea**: la junta dijo "admin debe poder abrir/ver el
documento subido" antes de aprobar/rechazar. Hoy se decide a ciegas
sobre metadatos.

**Archivos**:

1. [`apps/web/app/admin/reviewer/[submission_id]/page.tsx`](apps/web/app/admin/reviewer/[submission_id]/page.tsx) — replicar el patrón del proveedor:
   - Importar el `SubmissionPreview` de
     [`apps/web/app/portal/submissions/[submission_id]/page.tsx:497-600`](apps/web/app/portal/submissions/[submission_id]/page.tsx) y exportarlo a un módulo compartido (`apps/web/components/checkwise/submission-preview.tsx`).
   - Montar el visor arriba del `<ReviewDecisionPanel />`.
   - Usar el mismo endpoint backend, pero con sesión admin (no portal).

2. **Backend** — verificar que existe un endpoint admin para descargar
   el documento (similar a `submissionDownloadUrl` del proveedor pero
   con guard `internal_admin`/`reviewer`). Si no existe, añadirlo en
   [`apps/api/app/api/v1/reviewer.py`](apps/api/app/api/v1/reviewer.py).

**Aceptación**:

- En `/admin/reviewer/[id]`, el PDF se renderiza inline.
- El admin puede aprobar/rechazar **después** de revisar visualmente.
- 922 tests pasan + un nuevo test que verifica que el endpoint
  responde 200 con `internal_admin` y 403 sin rol.

**Tiempo**: 3-4 h (incluye refactor del componente + endpoint backend
+ test).

> Mitigación si no da tiempo: añadir un botón "Descargar PDF" en la
> pantalla admin que use el mismo endpoint del proveedor con un guard
> distinto. Menos elegante, pero desbloquea Monday.

---

## Pre-Monday smoke test

Después de aplicar P0-1 a P0-5 (o el subset que el tiempo permita):

```bash
# Frontend
cd apps/web
npm run typecheck
npm run lint
npm run check:print
npm run check:intents
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1 npm run build

# Backend
cd ../api
./.venv/bin/python -m pytest tests -q
```

**Esperado**: typecheck/lint/build verdes, 922+ tests pasando.

---

## Items P1 que NO bloquean Monday pero deben planearse

Estos están en [`_archive/handoffs-2026-05/FRIDAY_MEETING_ACTION_MATRIX.md`](_archive/handoffs-2026-05/FRIDAY_MEETING_ACTION_MATRIX.md). En orden de prioridad para post-Monday:

1. WhatsApp integración (montar `SupportCard` + env).
2. Form `/client/onboarding` self-service post-pago.
3. Cliente calendar con íconos y drill-down.
4. Sidebar plegable en desktop.
5. Dropdown de perfil estilo LinkedIn.
6. Bulk ZIP en superficie admin (`/admin/vendors/[id]` → "Descargar expediente").
7. Activar flag `MULTI_FILE_UPLOAD_ENABLED` y comunicar.
8. Sustituir copy `v0-draft` por textos firmados de Paco/Beko.

---

## Items que se comunican a testers (no se "fixean" pre-Monday)

- Las páginas legales muestran "DRAFT". Comunicar que el copy final
  llega esta semana.
- Multi-archivo está apagado. Testers cargan un archivo a la vez.
- Notificaciones llegan in-app; aún no por email/WhatsApp.
- Admin no descarga ZIP desde su superficie (todavía).
- Reportes Phase 3.3+ (AI generation) deferido.

---

## Riesgo si nada se fixea

| P0 sin fix | Riesgo concreto |
|------------|----------------|
| `posible_mismatch` inconsistente | Tester confundido, percepción de plataforma a medio terminar |
| Badge enum crudo | Tester ve `pendiente_revision` literal — daño de marca |
| `{new_status}` crudo en admin | Isaac/Paco lo verán y nos dirán |
| Admin sin visor PDF | Isaac/Paco no aprueban/rechazan con confianza |
| Form admin sin email | No se puede contactar al cliente nuevo; flujo se traba |
