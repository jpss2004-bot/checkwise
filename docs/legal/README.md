# Documentos legales — CheckWise

Archivo de las versiones aprobadas de los tres documentos legales que
se exhiben en `/legal/*` y que **todo proveedor y todo cliente** debe
aceptar antes de entrar a su espacio.

| Documento | Ruta UI | Archivo aquí | Versión vigente | Fuente |
|-----------|---------|--------------|-----------------|--------|
| Política de privacidad | `/legal/privacidad` | [aviso-de-privacidad-v2.md](./aviso-de-privacidad-v2.md) | `v2` | `apps/web/app/legal/privacidad/page.tsx` |
| Términos de uso | `/legal/terminos` | [terminos-de-uso-v2.md](./terminos-de-uso-v2.md) | `v2` | `apps/web/app/legal/terminos/page.tsx` |
| Aviso de consentimiento informado | `/legal/consentimiento` | [aviso-de-consentimiento-v2.md](./aviso-de-consentimiento-v2.md) | `v2` | `apps/web/app/legal/consentimiento/page.tsx` |
| **Referencias jurídicas (fuentes y leyes citadas)** | — | [references.md](./references.md) | aplica a v1 | — |

> **v2 (3 de junio de 2026):** la revisión legal reposiciona a LegalShelf
> como **encargado** del tratamiento (ya no responsable; el responsable es
> la empresa contratante), actualiza el régimen a «la Ley» + Secretaría
> Anticorrupción y Buen Gobierno, enumera los datos sensibles y rehace el
> flujo ARCO. El texto en los archivos `*-v2.md` es la copia íntegra
> firmada (reproducida tal cual, incluidas sus erratas; ver la lista de
> erratas reportadas al equipo legal). La fuente canónica viva es el JSX.
> Las versiones `v1` se conservan en sus archivos `*-v1.md`.

## Cómo se versiona

La versión canónica de los tres documentos vive en el backend en la
constante `CURRENT_LEGAL_CONSENT_VERSION`
(`apps/api/app/api/v1/portal.py`). El frontend la lee a través del
endpoint de sesión y la compara contra el valor almacenado para
decidir si el usuario debe re-aceptar:

- **Proveedores:** `provider_workspaces.legal_consent_version` (gate en
  `/portal/entra-a-tu-espacio`).
- **Clientes (desde v2):** `users.legal_consent_version` (gate en
  `/client/consentimiento`, expuesto en `GET /api/v1/client/me`). El
  cliente acepta una vez por versión, registrando IP y user-agent en
  `audit_log` con `action='client.legal_consent_accepted'`.

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

## Para el equipo legal

Cuando compartas estos cuatro documentos con un abogado externo,
manda el paquete completo:

1. [aviso-de-privacidad-v1.md](./aviso-de-privacidad-v1.md)
2. [terminos-de-uso-v1.md](./terminos-de-uso-v1.md)
3. [aviso-de-consentimiento-v1.md](./aviso-de-consentimiento-v1.md)
4. [references.md](./references.md) — leyes, artículos y portales
   oficiales que sustentan cada sección de los tres documentos.

El archivo de referencias mapea sección por sección con el
fundamento jurídico mexicano correspondiente (LFPDPPP, LFT 2021,
CFF, LSS, INFONAVIT, Código Civil Federal, Código de Comercio,
Ley Federal del Derecho de Autor) y enumera los portales oficiales
(INAI, DOF, SAT, STPS, REPSE, IMSS, INFONAVIT) para verificación
independiente.

## Historial de versiones

- **v2** — revisión legal del 3 de junio de 2026 (vigente desde
  2026-06-03). Reposiciona a LegalShelf como encargado, actualiza el
  régimen legal, enumera datos sensibles y rehace ARCO. Primera versión
  exigida también a los `client_admin`, no solo a proveedores.
- **v1** — primera versión aprobada por Paco/Beko, vigente desde
  2026-05-25.
- **v0-draft** — borrador interno (22 de mayo de 2026), nunca expuesto
  a clientes pagados.
