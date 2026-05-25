# Documentos legales — CheckWise

Archivo de las versiones aprobadas de los tres documentos legales que
se exhiben en `/legal/*` y que el proveedor debe aceptar antes de
entrar a su espacio.

| Documento | Ruta UI | Archivo aquí | Versión vigente | Fuente |
|-----------|---------|--------------|-----------------|--------|
| Aviso de privacidad integral | `/legal/privacidad` | [aviso-de-privacidad-v1.md](./aviso-de-privacidad-v1.md) | `v1` | `apps/web/app/legal/privacidad/page.tsx` |
| Términos de uso | `/legal/terminos` | [terminos-de-uso-v1.md](./terminos-de-uso-v1.md) | `v1` | `apps/web/app/legal/terminos/page.tsx` |
| Aviso de consentimiento informado | `/legal/consentimiento` | [aviso-de-consentimiento-v1.md](./aviso-de-consentimiento-v1.md) | `v1` | `apps/web/app/legal/consentimiento/page.tsx` |

## Cómo se versiona

La versión canónica de los tres documentos vive en el backend en la
constante `CURRENT_LEGAL_CONSENT_VERSION`
(`apps/api/app/api/v1/portal.py`). El frontend la lee a través del
endpoint `GET /api/v1/portal/session` y la compara contra el valor
almacenado en `provider_workspaces.legal_consent_version` para
decidir si el usuario debe re-aceptar.

Cuando se publica una nueva versión de cualquiera de los tres
documentos:

1. Editar el JSX correspondiente bajo `apps/web/app/legal/<doc>/page.tsx` con el texto nuevo, actualizando `version=` y `effectiveDate=`.
2. Bumpear `CURRENT_LEGAL_CONSENT_VERSION` en el backend al nuevo valor (por ejemplo `v2`).
3. Archivar una copia inmutable bajo `docs/legal/<doc>-vN.md` con el texto íntegro y la fecha de aprobación.
4. Actualizar la tabla de arriba.

Los aceptantes de la versión anterior verán automáticamente la
pantalla de consent en su siguiente entrada al portal y la nueva
aceptación quedará registrada en `audit_log` con
`action='provider.legal_consent_accepted'` y la versión nueva en
`metadata.version`.

## Historial de versiones

- **v1** — primera versión aprobada por Paco/Beko, vigente desde
  2026-05-25.
- **v0-draft** — borrador interno (22 de mayo de 2026), nunca expuesto
  a clientes pagados.
