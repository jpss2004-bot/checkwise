"""Build the customer-facing notification system overview PDF.

One-shot script — renders the Phase 7 notification fabric explainer
to PDF using the same Playwright pattern as
``app/services/reports/export.py``. Output lands at
``checkwise/outputs/Notificaciones_CheckWise_v2.pdf``.

Run from the apps/api directory:

    .venv/bin/python scripts/build_notifications_pdf.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

OUTPUT_FILENAME = "Notificaciones_CheckWise_v2.pdf"


HTML = r"""<!DOCTYPE html>
<html lang="es-MX">
<head>
<meta charset="utf-8" />
<title>CheckWise — Centro de notificaciones</title>
<style>
  @page {
    size: Letter;
    margin: 0;
  }
  :root {
    --navy: #0F1F3A;
    --text: #1A1F2E;
    --muted: #5A6478;
    --border: #E1E5EC;
    --bg: #FFFFFF;
    --callout-blue-bg: #ECF2FA;
    --callout-blue-border: #1E5A9C;
    --callout-green-bg: #E6F4EA;
    --callout-green-border: #138652;
    --callout-amber-bg: #FFF6E0;
    --callout-amber-border: #B8740C;
    --row-stripe: #F7F8FA;
    --critical: #B3261E;
    --important: #B8740C;
    --info: #5A6478;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    color: var(--text);
    background: var(--bg);
    font-family: -apple-system, BlinkMacSystemFont, "Inter", "Helvetica Neue",
      Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.4;
  }
  .page {
    width: 8.5in;
    height: 11in;
    padding: 0.5in 0.6in 0.5in 0.6in;
    page-break-after: always;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .page:last-child { page-break-after: auto; }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 8px;
    border-bottom: 1.5px solid var(--navy);
    margin-bottom: 16px;
    flex-shrink: 0;
  }
  .header .brand {
    font-weight: 700;
    font-size: 11pt;
    letter-spacing: -0.01em;
    color: var(--navy);
  }
  .header .doc {
    font-size: 8.5pt;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  h1 {
    font-size: 22pt;
    font-weight: 700;
    color: var(--navy);
    margin: 0 0 4px;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }
  .lead {
    color: var(--muted);
    font-size: 10pt;
    margin: 0 0 12px;
  }
  h2 {
    font-size: 12.5pt;
    font-weight: 700;
    color: var(--navy);
    margin: 14px 0 6px;
    letter-spacing: -0.01em;
  }
  h2:first-of-type { margin-top: 0; }
  p {
    margin: 0 0 8px;
  }
  ul, ol {
    margin: 0 0 8px;
    padding-left: 16px;
  }
  li {
    margin-bottom: 2px;
  }
  .callout {
    border-left: 3px solid var(--callout-blue-border);
    background: var(--callout-blue-bg);
    padding: 8px 12px;
    margin: 6px 0 12px;
    font-size: 9.5pt;
    border-radius: 0 4px 4px 0;
  }
  .callout.green {
    border-left-color: var(--callout-green-border);
    background: var(--callout-green-bg);
  }
  .callout.amber {
    border-left-color: var(--callout-amber-border);
    background: var(--callout-amber-bg);
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 4px 0 10px;
    font-size: 9.5pt;
  }
  th {
    background: var(--navy);
    color: #fff;
    text-align: left;
    padding: 6px 9px;
    font-weight: 600;
    font-size: 9.5pt;
  }
  td {
    padding: 6px 9px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }
  tr:nth-child(even) td { background: var(--row-stripe); }
  .pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 8.5pt;
    font-weight: 600;
    letter-spacing: 0.01em;
  }
  .pill.red { background: #FCE8E6; color: var(--critical); }
  .pill.amber { background: var(--callout-amber-bg); color: var(--important); }
  .pill.gray { background: #ECEEF2; color: var(--muted); }
  .footer {
    margin-top: auto;
    padding-top: 10px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    font-size: 8.5pt;
    color: var(--muted);
    flex-shrink: 0;
  }
  .grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin: 6px 0 10px;
  }
  .card {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
  }
  .card .label {
    font-size: 8pt;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 3px;
    font-weight: 600;
  }
  .card .value {
    font-size: 10pt;
    color: var(--text);
    line-height: 1.35;
  }
  strong { color: var(--navy); }
  .content { flex: 1; }
</style>
</head>
<body>

<!-- ───────── Page 1 — intro + ¿Qué? ───────── -->
<section class="page">
  <div class="header">
    <div class="brand">CheckWise</div>
    <div class="doc">Centro de notificaciones · versión 2</div>
  </div>
  <div class="content">
    <h1>Centro de notificaciones</h1>
    <p class="lead">
      Cómo te avisamos en CheckWise — qué tipo de avisos enviamos,
      cuándo, por qué canal, y cómo decides tú lo que quieres recibir.
    </p>

    <div class="callout">
      <strong>El centro de notificaciones dentro de CheckWise es la
      fuente canónica.</strong> Todo lo que el sistema te envía
      aparece ahí. El correo y WhatsApp existen para que te enteres
      aunque no entres a la plataforma — son un refuerzo, no la
      fuente principal.
    </div>

    <h2>¿Qué notificaciones recibes?</h2>
    <p>
      CheckWise agrupa todos sus avisos en cinco familias. Cada
      familia tiene un disparador claro: una fecha, un cambio de
      estado, o una acción que requiere tu intervención.
    </p>

    <table>
      <thead>
        <tr>
          <th style="width:26%">Familia</th>
          <th>Qué dispara el aviso</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Renovaciones REPSE</strong></td>
          <td>Tus documentos del expediente REPSE (Constancia de
          Situación Fiscal, registro patronal IMSS, constancia STPS) se
          acercan a su fecha de renovación o ya vencieron.</td>
        </tr>
        <tr>
          <td><strong>Reportes periódicos</strong></td>
          <td>Se abre o está por cerrar la ventana para reportar
          documentación mensual (IMSS, SAT), bimestral (INFONAVIT) o
          trimestral (SISUB, ICSOE).</td>
        </tr>
        <tr>
          <td><strong>Revisión de documentos</strong></td>
          <td>El equipo de Legal Shelf aprobó, rechazó o pidió
          aclaración sobre un documento que subiste.</td>
        </tr>
        <tr>
          <td><strong>Cuenta y bienvenida</strong></td>
          <td>Invitaciones a la plataforma, restablecimiento de
          contraseña, confirmación de canal o de tu número de
          WhatsApp.</td>
        </tr>
        <tr>
          <td><strong>Soporte</strong></td>
          <td>Confirmaciones de tickets que abres con Legal Shelf y
          respuestas de los agentes.</td>
        </tr>
      </tbody>
    </table>

    <h2>¿Cuándo te avisamos?</h2>
    <p>
      Cada familia tiene su propio calendario. Te damos tiempo de
      reaccionar antes de la fecha, y te recordamos si ya pasó.
    </p>

    <table>
      <thead>
        <tr>
          <th style="width:30%">Familia</th>
          <th>Calendario de avisos</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Renovaciones REPSE</strong></td>
          <td>30 y 14 días antes (informativo), 7 días antes, el día
          del vencimiento, y luego 7, 14, 21 y 28 días vencido.</td>
        </tr>
        <tr>
          <td><strong>Reportes periódicos</strong></td>
          <td>Al abrir la ventana, 7 días antes del cierre, el día
          anterior, el día del cierre, y 3 días después si no
          subiste el documento.</td>
        </tr>
        <tr>
          <td><strong>Revisión, cuenta y soporte</strong></td>
          <td>Al instante en que ocurre el evento — recibido,
          aprobado, rechazado, invitación enviada, ticket abierto.</td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="footer">
    <span>CheckWise · Centro de notificaciones</span>
    <span>Página 1 de 4</span>
  </div>
</section>

<!-- ───────── Page 2 — ¿A quién? + ¿Por qué canal? ───────── -->
<section class="page">
  <div class="header">
    <div class="brand">CheckWise</div>
    <div class="doc">Centro de notificaciones · versión 2</div>
  </div>
  <div class="content">
    <h2>¿A quién llegan los avisos?</h2>
    <p>Cada aviso llega a uno o dos destinatarios, según el evento:</p>
    <ul>
      <li><strong>El proveedor</strong> — la persona dueña del
      workspace en CheckWise (quien firmó el alta inicial).</li>
      <li><strong>El cliente</strong> — el responsable del portafolio
      de proveedores en la empresa contratante.</li>
    </ul>
    <p>
      Las renovaciones y los reportes críticos llegan a ambos. Las
      decisiones de revisión llegan al proveedor (con copia al cliente
      cuando es una aprobación o el reporte ya está vencido). Las
      notificaciones de cuenta llegan solo a quien le aplican.
    </p>
    <div class="callout green">
      Si un destinatario falla o no está disponible, eso nunca bloquea
      el envío al otro. Cada destinatario se procesa de forma
      independiente.
    </div>

    <h2>¿Por qué canal te avisamos?</h2>
    <p>
      CheckWise opera con tres canales. Tú eliges cómo quieres recibir
      tus avisos al momento del alta y puedes cambiarlo cuando quieras
      desde tu perfil.
    </p>

    <table>
      <thead>
        <tr>
          <th style="width:24%">Canal</th>
          <th>Para qué sirve</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Centro de notificaciones</strong><br />
          <span class="pill gray">siempre activo</span></td>
          <td>La campana dentro de CheckWise. Es la fuente canónica:
          todos los avisos aparecen aquí, sin excepción, y no se
          puede desactivar.</td>
        </tr>
        <tr>
          <td><strong>Correo electrónico</strong></td>
          <td>Refuerzo por email para avisos accionables —
          renovaciones próximas, documentos rechazados, invitaciones,
          restablecimiento de contraseña.</td>
        </tr>
        <tr>
          <td><strong>WhatsApp</strong></td>
          <td>Refuerzo por WhatsApp para los mismos avisos
          accionables, usando plantillas pre-aprobadas por Meta.
          Requiere verificar tu número una sola vez.</td>
        </tr>
      </tbody>
    </table>

    <h2>Niveles de urgencia</h2>
    <p>
      No todos los avisos pesan igual. CheckWise clasifica cada aviso
      en uno de tres niveles, y eso determina qué canales se activan.
    </p>

    <table>
      <thead>
        <tr>
          <th style="width:18%">Nivel</th>
          <th>Qué significa</th>
          <th style="width:30%">Canales que se activan</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><span class="pill red">Crítico</span></td>
          <td>Requiere acción hoy. Documentos vencidos o rechazados,
          cierres de reporte, invitaciones, restablecimientos.</td>
          <td>Centro + correo (obligatorio) + WhatsApp si lo
          activaste.</td>
        </tr>
        <tr>
          <td><span class="pill amber">Importante</span></td>
          <td>Requiere acción esta semana. Recordatorios a 7 días,
          aperturas de ventana, documentos aprobados.</td>
          <td>Centro + tus canales preferidos, salvo que silencies
          esa categoría.</td>
        </tr>
        <tr>
          <td><span class="pill gray">Informativo</span></td>
          <td>Solo para que estés enterado. Recordatorios a 30 y 14
          días, confirmaciones de recepción, cambios de preferencia.</td>
          <td>Solo el centro de notificaciones. Nunca por correo ni
          WhatsApp.</td>
        </tr>
      </tbody>
    </table>

    <div class="callout amber">
      <strong>Por qué importa el nivel intermedio:</strong> los avisos
      informativos existen para que la campana no se vuelva ruido. Si
      todo fuera crítico, perderías la confianza en el sistema. Este
      nivel te mantiene al día sin interrumpirte.
    </div>
  </div>
  <div class="footer">
    <span>CheckWise · Centro de notificaciones</span>
    <span>Página 2 de 4</span>
  </div>
</section>

<!-- ───────── Page 3 — ¿Cómo elijo? ───────── -->
<section class="page">
  <div class="header">
    <div class="brand">CheckWise</div>
    <div class="doc">Centro de notificaciones · versión 2</div>
  </div>
  <div class="content">
    <h2>¿Cómo elijo cómo recibirlos?</h2>
    <p>
      Al momento de tu alta en CheckWise capturamos tu preferencia,
      y la puedes cambiar cuando quieras desde
      <strong>Mi perfil → Notificaciones</strong>.
    </p>

    <div class="grid-2">
      <div class="card">
        <div class="label">Paso 1 — verificación</div>
        <div class="value"><strong>Verificas tu número de WhatsApp</strong>
        con un código de 6 dígitos que te enviamos una sola vez al
        número que diste. Si no usas WhatsApp, sigues con correo.</div>
      </div>
      <div class="card">
        <div class="label">Paso 2 — canal preferido</div>
        <div class="value"><strong>Eliges cómo quieres recibirlos:</strong>
        solo correo, solo WhatsApp, o ambos. La opción recomendada es
        <em>ambos</em>.</div>
      </div>
      <div class="card">
        <div class="label">Paso 3 — opcional</div>
        <div class="value"><strong>Silencias categorías</strong> que no
        te interesa recibir por correo o WhatsApp (renovaciones,
        reportes, revisión, cuenta, soporte). Sin afectar el centro.</div>
      </div>
      <div class="card">
        <div class="label">Regla que no cambia</div>
        <div class="value">Los avisos <strong>críticos siempre llegan
        por correo</strong>, aunque hayas silenciado esa categoría. Es
        el respaldo de auditoría — no se puede desactivar.</div>
      </div>
    </div>

    <div class="callout">
      Esa regla del correo crítico existe por un motivo simple: si un
      documento vence o se rechaza, debe quedar evidencia verificable
      de que CheckWise te avisó. El correo es el respaldo formal que
      un auditor externo puede inspeccionar.
    </div>

    <h2>Centro de notificaciones dentro de la plataforma</h2>
    <p>
      Cuando entras a CheckWise, la campana arriba a la derecha
      muestra los avisos pendientes. El centro tiene tres pestañas:
    </p>

    <table>
      <thead>
        <tr>
          <th style="width:22%">Pestaña</th>
          <th>Qué muestra</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Pendientes</strong></td>
          <td>Por defecto. Solo lo que requiere tu atención —
          críticos sin resolver y importantes sin leer.</td>
        </tr>
        <tr>
          <td><strong>Todas</strong></td>
          <td>Todo lo que el sistema te envió, incluyendo los
          informativos.</td>
        </tr>
        <tr>
          <td><strong>Resueltas</strong></td>
          <td>Avisos que ya cerraste, o que se resolvieron solos
          porque subiste el documento que faltaba.</td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="footer">
    <span>CheckWise · Centro de notificaciones</span>
    <span>Página 3 de 4</span>
  </div>
</section>

<!-- ───────── Page 4 — Centro UX + Trazabilidad + Resumen ───────── -->
<section class="page">
  <div class="header">
    <div class="brand">CheckWise</div>
    <div class="doc">Centro de notificaciones · versión 2</div>
  </div>
  <div class="content">
    <h2>Comportamientos del centro</h2>
    <p>Tres reglas que vale la pena conocer:</p>
    <ul>
      <li><strong>Se agrupa por documento y proveedor.</strong> Si un
      mismo documento cruza varios umbrales (7 días antes, día del
      vencimiento, 7 días vencido), ves <em>una sola tarjeta</em> que
      se actualiza — no siete tarjetas separadas.</li>
      <li><strong>La campana solo cuenta lo accionable.</strong> Los
      avisos informativos aparecen pero no inflan el contador, para
      que el número siempre signifique algo.</li>
      <li><strong>Los avisos informativos se ocultan solos</strong>
      después de 14 días si no los abriste. Los críticos permanecen
      hasta que el evento se resuelva.</li>
    </ul>

    <h2>¿Qué dice cada aviso?</h2>
    <p>
      Todos los avisos comparten una misma estructura, en español
      claro, sin tecnicismos:
    </p>
    <ul>
      <li>El nombre del proveedor o razón social.</li>
      <li>El nombre del documento o evento — por ejemplo,
      "Constancia REPSE" o "Reporte mensual SAT".</li>
      <li>La fecha relevante en formato día/mes/año.</li>
      <li>El estado — "próximo a vencer en 7 días", "vencido hace
      14 días", "aprobado", "se requiere aclaración".</li>
      <li>Una acción sugerida — el enlace directo dentro de
      CheckWise para que resuelvas el aviso en un clic.</li>
    </ul>

    <h2>Trazabilidad</h2>
    <p>
      Cada intento de envío queda registrado de forma permanente,
      sin importar el resultado. Por cada aviso guardamos:
    </p>
    <ul>
      <li>Fecha y hora exactas del intento.</li>
      <li>Destinatario al que se dirigió.</li>
      <li>Canal usado: centro, correo, o WhatsApp.</li>
      <li>Resultado: entregado, omitido (con la razón) o fallido
      (con el error técnico).</li>
    </ul>

    <div class="callout">
      <strong>Tres reglas que vale la pena recordar:</strong>
      <ol style="margin: 6px 0 0 18px; padding: 0;">
        <li>La campana dentro de CheckWise siempre tiene la verdad.
        Correo y WhatsApp son refuerzos.</li>
        <li>Tú decides los canales y puedes silenciar categorías —
        salvo el correo de avisos críticos.</li>
        <li>Si un aviso es crítico, lo recibirás en todos los canales
        activos. Si es informativo, solo lo verás en la campana.</li>
      </ol>
    </div>

    <p style="margin-top: 14px; color: var(--muted); font-size: 9.5pt;">
      ¿Preguntas? Escríbenos a <strong>hola@legalshelf.mx</strong> o
      usa <em>Reportar problema</em> dentro de la plataforma.
    </p>
  </div>
  <div class="footer">
    <span>CheckWise · Centro de notificaciones</span>
    <span>Página 4 de 4</span>
  </div>
</section>

</body>
</html>
"""


def main() -> None:
    # outputs/ lives at the workspace root, two levels above apps/api.
    output_dir = Path(__file__).resolve().parents[3] / "outputs"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / OUTPUT_FILENAME

    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, prefix="cw-notif-"
    ) as tmp:
        tmp.write(HTML.encode("utf-8"))
        tmp_path = Path(tmp.name)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page()
                page.goto(f"file://{tmp_path}", wait_until="networkidle")
                pdf_bytes = page.pdf(
                    format="Letter",
                    print_background=True,
                    margin={
                        "top": "0in",
                        "right": "0in",
                        "bottom": "0in",
                        "left": "0in",
                    },
                )
            finally:
                browser.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    output_path.write_bytes(pdf_bytes)
    print(f"wrote {output_path} ({len(pdf_bytes):,} bytes)")


if __name__ == "__main__":
    main()
