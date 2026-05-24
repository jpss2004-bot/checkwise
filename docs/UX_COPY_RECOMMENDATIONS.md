# Recomendaciones de copy en español — CheckWise

Para usuarios mexicanos no técnicos (40–50 años, gestor de
cumplimiento que delega tareas a su asistente). Evita inglés, evita
enums crudos, evita siglas no explicadas.

---

## Estados de documento (canónicos)

Mantener un único término por estado, en todas las superficies.

| Enum backend | UI canónica recomendada | Tono semáforo |
|--------------|-------------------------|---------------|
| `pendiente`              | "Pendiente de carga"           | gris |
| `recibido`               | "Recibimos tu documento"       | azul |
| `pendiente_revision`     | "En revisión humana"           | amarillo |
| `prevalidado`            | "Pasó validaciones automáticas"| azul |
| `posible_mismatch`       | **"Posible inconsistencia"**   | amarillo |
| `aprobado`               | "Aprobado"                     | verde |
| `rechazado`              | "Requiere corrección"          | rojo |
| `vencido`                | "Vencido — sube uno actualizado" | rojo |
| `no_aplica`              | "No aplica"                    | gris |
| `requiere_aclaracion`    | "Requiere aclaración"          | amarillo |
| `excepcion_legal`        | "Aprobado bajo excepción legal"| verde claro |

Razones para "Requiere corrección" (no "Rechazado"): la junta dijo
que la palabra "Rechazado" se siente final. "Requiere corrección"
invita a actuar. Sigue siendo el mismo enum interno.

---

## Botones y CTAs

| Lugar | Hoy | Recomendado |
|-------|-----|-------------|
| Confirmación de carga | "Continúa con tu expediente" | (mantener) |
| Detalle de submission rechazada | "Corregir y volver a cargar" | (mantener; muy claro) |
| Login | "Iniciar sesión" | (mantener) |
| Activación | "Crear contraseña y entrar" | (mantener) |
| Cliente vendor detail descarga | "Descargar expediente" | Añadir tooltip "Archivo ZIP con todos los documentos del proveedor" |
| Admin reviewer decisión "approve" | "Aprobar" | (mantener) |
| Admin reviewer decisión "reject" | "Rechazar" | Renombrar a "**Pedir corrección**" en el botón. Internamente queda `reject`. |
| Admin reviewer decisión "request_clarification" | "Pedir aclaración" | (mantener) |
| Admin reviewer decisión "mark_exception" | "Marcar excepción legal" | (mantener) |

---

## Razones de rechazo (chips frecuentes)

Hoy el `review-decision-panel.tsx` tiene una lista de chips. Validar
que todos digan algo accionable. Ejemplos recomendados:

- "Documento ilegible" → "El PDF no se lee bien. Sube uno con mejor calidad."
- "RFC no coincide" → "El RFC del documento no coincide con el del proveedor."
- "Periodo incorrecto" → "El documento corresponde a otro periodo."
- "Documento incompleto" → "Faltan páginas o secciones del documento."
- "Documento expirado" → "El documento que subiste ya no está vigente."
- "Tipo de documento incorrecto" → "Este no es el documento que pide el requerimiento."

Cada chip debe ser una oración completa que el proveedor entienda
sin contexto adicional.

---

## Estados vacíos (empty states)

| Pantalla | Hoy | Recomendado |
|----------|-----|-------------|
| Provider dashboard sin obligaciones | "Todo al día" | "Por ahora no hay nada pendiente. Te avisamos cuando se acerque la siguiente fecha." |
| Provider notifications vacío | "Sin notificaciones" | "Aún no hay avisos. Te avisaremos aquí cuando el equipo de cumplimiento revise un documento o se acerque una fecha." |
| Client vendors vacío | "Sin proveedores" | "Aún no hay proveedores registrados. Comparte el link de invitación o pídeselo a tu admin de CheckWise." |
| Client submissions vacío | "Sin entregas" | "Aún no hay documentos cargados. Cuando tus proveedores entreguen, aparecerán aquí." |
| Admin reviewer queue vacío | "Cola vacía" | "Cero pendientes. Te avisamos cuando alguien suba algo nuevo." |

---

## Notificaciones — copy por tipo

### Provider notifications

| `notification_type` | Title (verde) | Body |
|---------------------|---------------|------|
| `submission_approved`         | "Tu documento fue aprobado" | "{requirement_name} para {period_label} ya quedó en regla." |
| `submission_rejected`         | "Necesitamos que corrijas un documento" | "{requirement_name}: {reason}. Toca para ver el detalle y volver a subir." |
| `submission_clarification`    | "El equipo necesita una aclaración" | "{requirement_name}: {reason}. Toca para responder." |
| `renewal_due_soon` (yellow)   | "Pronto vence un documento" | "Tu {requirement_name} se debe renovar en {days} días." |
| `renewal_overdue` (red)       | "Documento vencido por renovar" | "Tu {requirement_name} venció hace {days} días. Sube el más reciente." |

### Client notifications

| `notification_type` | Title | Body |
|---------------------|-------|------|
| `provider_uploaded` | "Tu proveedor entregó documentos" | "{vendor_name} entregó {n} documento(s). Revisaremos y te avisamos si hay algo que corregir." |
| `provider_overdue` (red) | "Un proveedor tiene documentos vencidos" | "{vendor_name} tiene {n} documento(s) vencidos." |
| `cycle_progress` (info) | "Avance del expediente" | "{vendor_name}: {pct}% completado. Aún faltan {n} documentos por entregar." |

---

## Calendario

### Labels institucionales (ya correctos)

| Code | Label UI | Ícono |
|------|----------|-------|
| `sat`         | "SAT"       | balanza |
| `imss`        | "IMSS"      | edificio |
| `infonavit`   | "INFONAVIT" | casa |
| `stps_repse`  | "STPS / REPSE" | escudo |

### Day cell tooltip

En vez de "Posible mismatch" o "Rechazado", usar:

- 🟢 "Aprobado"
- 🟡 "En revisión"
- 🟡 "Requiere aclaración"
- 🟡 "Posible inconsistencia"
- 🔴 "Requiere corrección"
- 🔴 "Vencido"
- ⚪ "Pendiente"

---

## Admin comments — guía para reviewers

El reviewer panel tiene un textarea para "Observaciones" (visible al
proveedor). Sugerencia de copy de ayuda:

> "Escribe lo que el proveedor necesita hacer para corregir el
> documento. Sé concreto: 'Sube el CFDI con sello completo' es mejor
> que 'Falta información'."

Ejemplos de buen texto de observación que se enseñen al reviewer:

- "El PDF está cortado en la página 2. Sube el archivo completo."
- "El RFC del documento dice ABCD850101XYZ y el del proveedor es WXYZ850101ABC. Verifica que sea el contrato correcto."
- "El periodo en el documento es abril 2026; este requerimiento pide mayo 2026."

---

## Instrucciones de upload

En `/portal/upload`, antes del dropzone, mostrar de un vistazo:

> **Sube el documento como PDF.**
> Si el archivo está protegido con contraseña, retírasela primero.
> Si el documento tiene anexos físicos (croquis, lista, etc.), súbelos
> juntos como un sólo PDF — o, si la opción multi-archivo está
> habilitada, súbelos como archivos adicionales.

(Cuando el flag multi-archivo se encienda, agregar el segundo párrafo
visible).

---

## Errores

| Caso | Hoy | Recomendado |
|------|-----|-------------|
| PDF > 15 MB | "Archivo demasiado grande" | "El archivo es de {X} MB; el máximo es 15 MB. Comprime o divide el PDF." |
| Archivo encriptado | "PDF protegido" | "Este PDF tiene contraseña. Retírala desde Acrobat o tu visor antes de subirlo." |
| Archivo dañado | "PDF corrupto" | "No pudimos abrir este PDF. Vuelve a exportarlo o pide el archivo original." |
| Mismatch detectado | "Posible mismatch" | "Detectamos que el documento podría no coincidir con este requerimiento. Si confías en que es el correcto, súbelo de cualquier forma y el equipo lo revisará. Si te equivocaste, vuelve a cargar el correcto." |

---

## Perfil de usuario (futuro)

Cuando se construya el dropdown estilo LinkedIn, sugerencia de
opciones:

- **Tu nombre** (no clickable)
- "Mi perfil"
- "Preferencias de aviso" (canal email/WhatsApp/ambos)
- "Soporte WhatsApp" (abre el deeplink)
- "Cambiar contraseña"
- "Cerrar sesión"

---

## Términos legales (cuando lleguen aprobados)

Al sustituir el copy `v0-draft`, mantener estas líneas que ya
funcionan bien:

- "Antes de entrar a tu espacio necesitamos que confirmes que leíste
  y aceptas estos tres documentos. Tu aceptación queda registrada
  para auditoría."
- "Estos documentos pueden actualizarse. Si cambia algo importante,
  te volveremos a pedir tu confirmación antes de entrar."

---

## Glosario interno → UI

Cosas que el equipo dice en Slack pero que el usuario nunca debe ver:

| Interno | UI |
|---------|----|
| "vendor"          | "proveedor" |
| "requirement code"| "obligación" o "institución" según contexto |
| "submission"      | "entrega" o "documento" según contexto |
| "workspace"       | "tu espacio" |
| "client"          | "empresa cliente" (para el proveedor) o "tu empresa" (para el cliente) |
| "load_type"       | "tipo de carga" (sólo en pantallas técnicas) |
| "period_key"      | "periodo" |
| "RFC normalizado" | "RFC" |
| "evidence slot"   | "obligación" |
| "supersedes"      | "reemplaza" |

---

## Tono general

- **Tú**, no **Usted** (la junta es muy clara: cercano y profesional).
- **Verbos en imperativo amable**: "Sube tu documento" no "Suba su
  documento", "Revisa el detalle" no "Por favor revise".
- **Frases cortas** (máximo 12 palabras). El público delega tareas;
  cada mensaje debe leerse en 3 segundos.
- **Cero jerga jurídica** salvo donde sea inevitable (REPSE, RFC,
  CSF, IMSS, INFONAVIT — esos sí se mantienen porque son los términos
  que el público ya usa todos los días).
