# Provider Portal Flow (V1.2)

CheckWise V1.2 introduces a guided provider journey on top of the V1.1 native
intake. The wizard is no longer the entry point: providers now arrive at an
access page, complete an Expediente Corporativo, and then operate over a
recurring REPSE calendar.

The single source of truth for what providers must upload is
`C.Árbol Plataforma Proveedores REPSE VF` (sheet "Árbol Plataforma"), encoded
in `apps/api/app/core/compliance_catalog.py` and exposed via
`/api/v1/compliance/*`. The portal endpoints at `/api/v1/portal/*` overlay
that catalog with each provider's actual submissions to compute "what's
missing vs received."

## Journey

```text
1. /                       Acceso de proveedor (cliente/filial/proveedor/RFC/persona/contrato)
2. /portal/onboarding      Expediente Corporativo + progreso
3. /portal/dashboard       Calendario REPSE 2026 (mensual / bimestral / cuatrimestral / anual)
4. /portal/upload          Wizard de carga prellenado desde el calendario o el expediente
```

## Components

| Surface | Role |
| --- | --- |
| `ProviderAccessForm` | Demo login / contexto inicial |
| `ProviderContextBar` | Sticky header con identidad de sesión |
| `OnboardingChecklist` | Expediente Corporativo agrupado por sección |
| `ComplianceCalendar` | Calendario anual con tarjetas mensuales por institución |
| `RequirementStatusBadge` | Estado documental homologado |
| `IntakeWizard` (V1.1) | Reutilizado en `/portal/upload`, acepta `prefill` |

## Backend

### Catálogo regulatorio (read-only)

- `GET /api/v1/compliance/catalog?year=2026`
- `GET /api/v1/compliance/onboarding?persona_type=moral`
- `GET /api/v1/compliance/calendar?year=2026&persona_type=moral`

Catálogo derivado de `C.Árbol Plataforma Proveedores REPSE VF`. Versión activa:
`CATALOG_VERSION` en `compliance_catalog.py`.

### Workspaces (demo state en DB)

- `POST /api/v1/portal/access` → crea/recupera workspace y emite `access_token`.
- `GET /api/v1/portal/workspaces/{id}` → contexto del workspace (header `X-Workspace-Token`).
- `GET /api/v1/portal/workspaces/{id}/onboarding` → expediente esperado vs recibido.
- `GET /api/v1/portal/workspaces/{id}/calendar?year=2026` → calendario esperado vs recibido.

⚠️ Estos endpoints **no implementan autenticación**. El `access_token` es un
opaque token guardado en `localStorage` del navegador como sesión demo. La
fase V1.3 debe sustituirlo por autenticación real (Clerk / Auth0 / Supabase),
roles y permisos.

## Modelo de datos

V1.2 añade:

- `provider_workspaces` (`id`, `client_id`, `vendor_id`, `contract_id?`,
  `filial_name`, `persona_type`, `display_name`, `access_token`,
  `onboarding_completed_at`, `status`).
- `vendors.persona_type` (`moral` | `fisica`, nullable, para no romper migraciones).

No se modifica la lógica de `submissions`; el dashboard compara expedientes y
calendario contra las submissions existentes del par `(client_id, vendor_id)`.

## Estado client-side

Sesión demo guardada en `localStorage` bajo la clave `checkwise.portal.session.v1`:

```ts
{
  workspace_id: string;
  access_token: string;
  persona_type: "moral" | "fisica";
  client_name: string;
  vendor_name: string;
  vendor_rfc: string;
  filial_name: string | null;
  contract_reference: string | null;
  onboarding_completed_at: string | null;
}
```

Helpers: `readPortalSession`, `writePortalSession`, `clearPortalSession`
(`apps/web/lib/portal-session.ts`).

## Reglas que se respetan

- **Sin aprobación legal automática**. Toda revisión sigue siendo humana.
- **Archivos siempre fuera de DB**. La carga sigue pasando por
  `POST /api/v1/submissions` y se guarda en storage local.
- **Catálogo versionado**. El Árbol se trata como regulación versionada; la
  semilla a `requirement_versions` queda pendiente para V1.3.
- **Demo aislada**. El botón "Usar PDF demo" sigue gated por
  `NEXT_PUBLIC_DEMO_MODE`.

## Pendiente para V1.3

1. Autenticación real (Clerk / Auth0 / Supabase) + roles cliente / proveedor / revisor.
2. Sembrar `requirements` y `requirement_versions` desde el catálogo.
3. Persistir el estado de onboarding (`onboarding_completed_at`) cuando el
   revisor cierra el alta inicial.
4. Reconciliar `period_code` con la taxonomía bimestral / cuatrimestral del
   Árbol (B1–B6, Q1–Q3) en lugar de un YYYY-MM libre.
5. Importador JotForm / Sheets que abra workspaces históricos.
6. Vista para el cliente con sus proveedores agregados.
