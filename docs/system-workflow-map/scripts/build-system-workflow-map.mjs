import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const __filename = fileURLToPath(import.meta.url);
const scriptDir = path.dirname(__filename);
const outDir = path.resolve(scriptDir, "..");
const diagramsDir = path.join(outDir, "diagrams");
const repoRoot = path.resolve(outDir, "../..");
const bundledNodeModules =
  "/Users/josepablosamano/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const require = createRequire(path.join(bundledNodeModules, "noop.js"));
const { chromium } = require("playwright");

const DATE = "19 de mayo de 2026";

const brand = {
  navy: "#013557",
  navy2: "#024069",
  navy3: "#02558a",
  teal: "#09c1b0",
  tealDark: "#058178",
  gray950: "#1b2638",
  gray700: "#374157",
  gray600: "#4a5670",
  gray500: "#5f6e87",
  gray300: "#b8c0d0",
  gray200: "#dde2ec",
  gray100: "#eef1f6",
  gray50: "#f7f9fb",
  white: "#ffffff",
  green: "#199641",
  amber: "#b87500",
  red: "#c32020",
  blue: "#2570e8",
  orange: "#d96d00",
};

const statusTone = {
  Implementado: { bg: "#e9f8f2", fg: "#176c3a", border: "#b9e4cb" },
  Parcial: { bg: "#fff7e6", fg: "#9a5b00", border: "#f1d49a" },
  Planeado: { bg: "#edf6ff", fg: "#0b5e9f", border: "#c9def5" },
  "Requiere validación": { bg: "#fff3e9", fg: "#b85f00", border: "#f0c9a4" },
  "Faltante recomendado": { bg: "#fff0f0", fg: "#aa1f1f", border: "#efb7b7" },
  "Documentado / no completo": { bg: "#f3f0ff", fg: "#5540a0", border: "#d5cdf4" },
};

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function wrap(text, max = 24) {
  const words = String(text).split(/\s+/);
  const lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (next.length > max && line) {
      lines.push(line);
      line = word;
    } else {
      line = next;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function textBlock({ x, y, text, size = 18, color = brand.gray950, weight = 600, max = 28, line = 22, anchor = "start" }) {
  const lines = wrap(text, max);
  return `<text x="${x}" y="${y}" fill="${color}" font-family="Inter, Open Sans, Arial, sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}">${lines
    .map((t, i) => `<tspan x="${x}" dy="${i === 0 ? 0 : line}">${esc(t)}</tspan>`)
    .join("")}</text>`;
}

function node({ x, y, w, h, title, subtitle = "", kind = "frontend", badge = "", max = 24 }) {
  const colors = {
    user: { fill: "#eef9f7", stroke: brand.teal, title: brand.navy },
    frontend: { fill: "#eff6fb", stroke: brand.navy3, title: brand.navy },
    backend: { fill: "#fff7e6", stroke: "#b87500", title: brand.navy },
    data: { fill: "#f7f9fb", stroke: brand.gray300, title: brand.navy },
    security: { fill: "#fff0f0", stroke: brand.red, title: brand.navy },
    report: { fill: "#edf6ff", stroke: brand.blue, title: brand.navy },
    decision: { fill: "#f9fbff", stroke: brand.teal, title: brand.navy },
    error: { fill: "#fff0f0", stroke: brand.red, title: brand.red },
  }[kind] || { fill: brand.white, stroke: brand.gray300, title: brand.navy };
  const titleLines = textBlock({ x: x + 18, y: y + 30, text: title, size: 18, color: colors.title, weight: 800, max, line: 20 });
  const subtitleLines = subtitle
    ? textBlock({ x: x + 18, y: y + 64, text: subtitle, size: 13, color: brand.gray600, weight: 500, max: max + 10, line: 16 })
    : "";
  const badgeEl = badge
    ? `<rect x="${x + w - 92}" y="${y + 12}" width="74" height="22" rx="11" fill="${statusTone[badge]?.bg || "#fff"}" stroke="${statusTone[badge]?.border || brand.gray200}"/><text x="${x + w - 55}" y="${y + 27}" text-anchor="middle" fill="${statusTone[badge]?.fg || brand.gray700}" font-family="Inter, Arial" font-size="9" font-weight="800">${esc(badge)}</text>`
    : "";
  return `<g>
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="14" fill="${colors.fill}" stroke="${colors.stroke}" stroke-width="2"/>
    ${titleLines}${subtitleLines}${badgeEl}
  </g>`;
}

function arrow({ x1, y1, x2, y2, color = brand.navy3, dashed = false, label = "" }) {
  const dash = dashed ? `stroke-dasharray="7 7"` : "";
  const midX = (x1 + x2) / 2;
  const midY = (y1 + y2) / 2;
  return `<g>
    <line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="2.4" ${dash} marker-end="url(#arrow)"/>
    ${label ? `<rect x="${midX - 74}" y="${midY - 18}" width="148" height="26" rx="13" fill="#ffffff" stroke="${brand.gray200}"/><text x="${midX}" y="${midY}" text-anchor="middle" fill="${brand.gray600}" font-family="Inter, Arial" font-size="11" font-weight="700">${esc(label)}</text>` : ""}
  </g>`;
}

function svgShell(title, body, height = 760) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="${height}" viewBox="0 0 1400 ${height}">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="${brand.navy3}"/>
    </marker>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#013557" flood-opacity=".10"/>
    </filter>
  </defs>
  <rect width="1400" height="${height}" fill="#ffffff"/>
  <text x="44" y="54" fill="${brand.navy}" font-family="Inter, Open Sans, Arial, sans-serif" font-size="26" font-weight="900">${esc(title)}</text>
  <line x1="44" y1="76" x2="1356" y2="76" stroke="${brand.gray200}" stroke-width="2"/>
  ${body}
</svg>`;
}

function write(file, contents) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, contents, "utf8");
}

const diagrams = new Map();

diagrams.set("01-system-overview.svg", svgShell("01 · Vista general del sistema", `
  ${node({ x: 54, y: 118, w: 190, h: 92, title: "Proveedor", subtitle: "Carga evidencia y atiende correcciones", kind: "user" })}
  ${node({ x: 54, y: 258, w: 190, h: 92, title: "Cliente", subtitle: "Consulta avance, riesgo y reportes", kind: "user" })}
  ${node({ x: 54, y: 398, w: 190, h: 92, title: "Revisor interno", subtitle: "Valida evidencia y decide estados", kind: "user" })}
  ${node({ x: 54, y: 538, w: 190, h: 92, title: "Admin", subtitle: "Opera catálogos, clientes y auditoría", kind: "user" })}
  ${node({ x: 322, y: 142, w: 220, h: 132, title: "Frontend Next.js", subtitle: "/login, /portal/*, /client/*, /admin/*", kind: "frontend" })}
  ${node({ x: 322, y: 362, w: 220, h: 132, title: "API FastAPI", subtitle: "/api/v1 con auth, portal, reviewer, admin, client, reports", kind: "backend" })}
  ${node({ x: 635, y: 110, w: 220, h: 92, title: "Auth/RBAC", subtitle: "JWT, roles, memberships, portal cookie", kind: "security" })}
  ${node({ x: 635, y: 245, w: 220, h: 92, title: "Intake documental", subtitle: "PDF, SHA-256, storage, inspección", kind: "backend" })}
  ${node({ x: 635, y: 380, w: 220, h: 92, title: "Revisión humana", subtitle: "Decisión, historial, eventos y audit_log", kind: "backend" })}
  ${node({ x: 635, y: 515, w: 220, h: 92, title: "Reportes", subtitle: "Contexto, snapshot, plan, bloques, versiones", kind: "report" })}
  ${node({ x: 960, y: 135, w: 230, h: 112, title: "PostgreSQL", subtitle: "Entidades, estados, auditoría y versiones", kind: "data" })}
  ${node({ x: 960, y: 330, w: 230, h: 112, title: "Storage", subtitle: "Archivos fuera de DB; local dev o S3/R2", kind: "data" })}
  ${node({ x: 960, y: 525, w: 230, h: 112, title: "Workers futuros", subtitle: "OCR, dedup, alertas, exports async", kind: "data", badge: "Planeado" })}
  ${arrow({ x1: 244, y1: 164, x2: 322, y2: 188 })}
  ${arrow({ x1: 244, y1: 304, x2: 322, y2: 208 })}
  ${arrow({ x1: 244, y1: 444, x2: 322, y2: 220 })}
  ${arrow({ x1: 244, y1: 584, x2: 322, y2: 240 })}
  ${arrow({ x1: 432, y1: 274, x2: 432, y2: 362, label: "fetch/REST/SSE" })}
  ${arrow({ x1: 542, y1: 428, x2: 635, y2: 156, label: "auth" })}
  ${arrow({ x1: 542, y1: 428, x2: 635, y2: 291, label: "uploads" })}
  ${arrow({ x1: 542, y1: 428, x2: 635, y2: 426, label: "review" })}
  ${arrow({ x1: 542, y1: 428, x2: 635, y2: 561, label: "reports" })}
  ${arrow({ x1: 855, y1: 291, x2: 960, y2: 386, label: "file bytes" })}
  ${arrow({ x1: 855, y1: 426, x2: 960, y2: 191, label: "status/audit" })}
  ${arrow({ x1: 855, y1: 561, x2: 960, y2: 191, label: "snapshots" })}
  ${arrow({ x1: 1190, y1: 386, x2: 1190, y2: 581, dashed: true, label: "futuro" })}
`, 720));

diagrams.set("02-auth-and-entry-flow.svg", svgShell("02 · Autenticación, entrada y redirecciones", `
  ${node({ x: 58, y: 126, w: 210, h: 92, title: "/login", subtitle: "Superficie única de login", kind: "frontend" })}
  ${node({ x: 338, y: 126, w: 245, h: 92, title: "POST /auth/login", subtitle: "Email + password → JWT, roles, orgs, must_change_password", kind: "backend" })}
  ${node({ x: 656, y: 88, w: 230, h: 86, title: "/activate", subtitle: "Cambio forzado de contraseña", kind: "frontend" })}
  ${node({ x: 656, y: 218, w: 230, h: 86, title: "/admin/reviewer", subtitle: "internal_admin o reviewer", kind: "frontend" })}
  ${node({ x: 656, y: 348, w: 230, h: 86, title: "/client/dashboard", subtitle: "client_admin", kind: "frontend" })}
  ${node({ x: 656, y: 478, w: 230, h: 86, title: "/portal/entra-a-tu-espacio", subtitle: "provider workspace owner", kind: "frontend" })}
  ${node({ x: 990, y: 88, w: 250, h: 86, title: "POST /auth/set-password", subtitle: "Actualiza bcrypt y limpia must_change_password", kind: "backend" })}
  ${node({ x: 990, y: 218, w: 250, h: 86, title: "AdminShell / ClientShell", subtitle: "Sin JWT → /login; rol incorrecto → /admin fallback", kind: "security" })}
  ${node({ x: 990, y: 348, w: 250, h: 86, title: "POST /portal/enter", subtitle: "Valida owner_user_id, rota access_token y setea cookie httpOnly", kind: "backend" })}
  ${node({ x: 990, y: 478, w: 250, h: 86, title: "GET /portal/me", subtitle: "JWT, cookie o X-Workspace-Token legacy", kind: "backend" })}
  ${node({ x: 104, y: 386, w: 250, h: 86, title: "/admin/login", subtitle: "Legacy redirect a /login", kind: "frontend", badge: "Parcial" })}
  ${node({ x: 104, y: 518, w: 250, h: 86, title: "Rutas protegidas sin sesión", subtitle: "/admin/*, /client/*, /portal/* → /login", kind: "security" })}
  ${arrow({ x1: 268, y1: 172, x2: 338, y2: 172 })}
  ${arrow({ x1: 583, y1: 172, x2: 656, y2: 131, label: "must_change" })}
  ${arrow({ x1: 583, y1: 172, x2: 656, y2: 261, label: "staff" })}
  ${arrow({ x1: 583, y1: 172, x2: 656, y2: 391, label: "client" })}
  ${arrow({ x1: 583, y1: 172, x2: 656, y2: 521, label: "provider" })}
  ${arrow({ x1: 886, y1: 131, x2: 990, y2: 131 })}
  ${arrow({ x1: 886, y1: 521, x2: 990, y2: 391 })}
  ${arrow({ x1: 1115, y1: 434, x2: 1115, y2: 478 })}
  ${arrow({ x1: 354, y1: 429, x2: 656, y2: 172, dashed: true, label: "redirect" })}
  ${arrow({ x1: 354, y1: 561, x2: 656, y2: 172, dashed: true, label: "guard" })}
  ${node({ x: 496, y: 588, w: 600, h: 88, title: "Hallazgo P1", subtitle: "Cancelar en /activate puede conservar JWT temporal y rebotar al portal; documentado en redirect_matrix.csv.", kind: "error", max: 52 })}
`, 720));

diagrams.set("03-supplier-upload-flow.svg", svgShell("03 · Flujo de proveedor y carga documental", `
  ${node({ x: 44, y: 118, w: 185, h: 86, title: "/portal/dashboard", subtitle: "Ve semáforo, acciones y faltantes", kind: "frontend" })}
  ${node({ x: 270, y: 118, w: 185, h: 86, title: "/portal/onboarding", subtitle: "Checklist por requisito", kind: "frontend" })}
  ${node({ x: 496, y: 118, w: 185, h: 86, title: "/portal/upload", subtitle: "Selecciona periodo, institución, requisito y PDF", kind: "frontend" })}
  ${node({ x: 722, y: 92, w: 208, h: 86, title: "Pre-check browser", subtitle: "SHA-256 opcional y duplicate-check", kind: "frontend" })}
  ${node({ x: 722, y: 210, w: 208, h: 86, title: "POST /portal/.../submissions", subtitle: "Tenant identity desde workspace, no desde form", kind: "backend" })}
  ${node({ x: 984, y: 92, w: 190, h: 86, title: "Storage", subtitle: "Local o S3/R2; storage_key y bytes", kind: "data" })}
  ${node({ x: 984, y: 210, w: 190, h: 86, title: "PDF inspection", subtitle: "Cabecera PDF, cifrado, páginas, texto", kind: "backend" })}
  ${node({ x: 984, y: 328, w: 190, h: 86, title: "Document intelligence", subtitle: "Señales determinísticas: institución, tipo, RFC, periodo", kind: "backend" })}
  ${node({ x: 722, y: 446, w: 208, h: 86, title: "DB writes", subtitle: "Submission, Document, Inspection, Validation, Events, History, AuditLog", kind: "data" })}
  ${node({ x: 496, y: 446, w: 185, h: 86, title: "Estado inicial", subtitle: "pendiente_revision, posible_mismatch o requiere_aclaracion", kind: "decision" })}
  ${node({ x: 270, y: 446, w: 185, h: 86, title: "/portal/submissions/[id]", subtitle: "Detalle, motivos, historial y reintentos", kind: "frontend" })}
  ${node({ x: 44, y: 446, w: 185, h: 86, title: "Excepciones", subtitle: "PDF inválido, tamaño, MIME, unauthorized, mismatch, duplicado", kind: "error" })}
  ${arrow({ x1: 229, y1: 161, x2: 270, y2: 161 })}
  ${arrow({ x1: 455, y1: 161, x2: 496, y2: 161 })}
  ${arrow({ x1: 681, y1: 161, x2: 722, y2: 135, label: "hash" })}
  ${arrow({ x1: 826, y1: 178, x2: 826, y2: 210 })}
  ${arrow({ x1: 930, y1: 253, x2: 984, y2: 135, label: "save" })}
  ${arrow({ x1: 930, y1: 253, x2: 984, y2: 253, label: "inspect" })}
  ${arrow({ x1: 1079, y1: 296, x2: 1079, y2: 328 })}
  ${arrow({ x1: 984, y1: 371, x2: 930, y2: 489, label: "signals" })}
  ${arrow({ x1: 722, y1: 489, x2: 681, y2: 489 })}
  ${arrow({ x1: 496, y1: 489, x2: 455, y2: 489 })}
  ${arrow({ x1: 270, y1: 489, x2: 229, y2: 489, dashed: true, label: "feedback" })}
  ${arrow({ x1: 826, y1: 296, x2: 148, y2: 446, dashed: true, label: "error paths" })}
`, 720));

diagrams.set("04-internal-review-flow.svg", svgShell("04 · Flujo de revisión interna/legal", `
  ${node({ x: 50, y: 132, w: 210, h: 86, title: "/admin/reviewer", subtitle: "Queue FIFO; reviewer o internal_admin", kind: "frontend" })}
  ${node({ x: 315, y: 132, w: 230, h: 86, title: "GET /reviewer/queue", subtitle: "Filtra pendiente_revision y posible_mismatch", kind: "backend" })}
  ${node({ x: 600, y: 132, w: 220, h: 86, title: "/admin/reviewer/[id]", subtitle: "Detalle, PDF metadata, eventos e historial", kind: "frontend" })}
  ${node({ x: 875, y: 132, w: 230, h: 86, title: "GET /reviewer/submissions/{id}", subtitle: "Cross-tenant solo para staff autorizado", kind: "backend" })}
  ${node({ x: 315, y: 330, w: 230, h: 86, title: "Decisión humana", subtitle: "approve, reject, request_clarification, mark_exception", kind: "decision" })}
  ${node({ x: 600, y: 330, w: 220, h: 86, title: "POST /reviewer/.../decision", subtitle: "Valida acción y estado origen", kind: "backend" })}
  ${node({ x: 875, y: 300, w: 230, h: 86, title: "Transición atómica", subtitle: "Submission.status + Document.status", kind: "backend" })}
  ${node({ x: 875, y: 430, w: 230, h: 86, title: "Trazabilidad", subtitle: "DocumentStatusHistory, ValidationEvent, AuditLog", kind: "data" })}
  ${node({ x: 1148, y: 300, w: 200, h: 86, title: "Visibilidad", subtitle: "Proveedor, cliente y reportes leen estado actualizado", kind: "report" })}
  ${node({ x: 50, y: 506, w: 230, h: 86, title: "Errores", subtitle: "404 submission, 409 terminal/estado no permitido, 422 razón faltante", kind: "error" })}
  ${arrow({ x1: 260, y1: 175, x2: 315, y2: 175 })}
  ${arrow({ x1: 545, y1: 175, x2: 600, y2: 175 })}
  ${arrow({ x1: 820, y1: 175, x2: 875, y2: 175 })}
  ${arrow({ x1: 710, y1: 218, x2: 430, y2: 330, label: "revisar" })}
  ${arrow({ x1: 545, y1: 373, x2: 600, y2: 373 })}
  ${arrow({ x1: 820, y1: 373, x2: 875, y2: 343 })}
  ${arrow({ x1: 990, y1: 386, x2: 990, y2: 430 })}
  ${arrow({ x1: 1105, y1: 343, x2: 1148, y2: 343 })}
  ${arrow({ x1: 1105, y1: 473, x2: 1148, y2: 386, label: "read models" })}
  ${arrow({ x1: 600, y1: 416, x2: 280, y2: 549, dashed: true, label: "errores" })}
`, 720));

diagrams.set("05-reporting-flow.svg", svgShell("05 · Flujo de reportes y asistencia IA", `
  ${node({ x: 58, y: 118, w: 205, h: 86, title: "Rutas reports", subtitle: "/admin/reports, /client/reports, /portal/reports", kind: "frontend" })}
  ${node({ x: 312, y: 118, w: 218, h: 86, title: "GET /reports/_presets", subtitle: "Presets filtrados por roles/audiencia", kind: "backend" })}
  ${node({ x: 580, y: 118, w: 218, h: 86, title: "POST /reports/from-preset", subtitle: "Crea Report + v1 vacía", kind: "backend" })}
  ${node({ x: 848, y: 118, w: 218, h: 86, title: "Editor", subtitle: "Canvas, Save version, Print, Copilot", kind: "frontend" })}
  ${node({ x: 1120, y: 118, w: 218, h: 86, title: "GET /reports/_engine", subtitle: "mock o anthropic; banner honesto", kind: "backend" })}
  ${node({ x: 312, y: 322, w: 218, h: 86, title: "POST /reports/{id}/plan", subtitle: "Context snapshot + plan estructurado", kind: "backend" })}
  ${node({ x: 580, y: 322, w: 218, h: 86, title: "Context Assembler", subtitle: "Scope server-side, sanitizer PII, ComplianceSnapshot", kind: "security" })}
  ${node({ x: 848, y: 322, w: 218, h: 86, title: "Planner LLM", subtitle: "Tool-use; no inventa bloques; mock fallback", kind: "report" })}
  ${node({ x: 1120, y: 322, w: 218, h: 86, title: "POST /generate SSE", subtitle: "plan → block_start → data → AI delta → version_saved", kind: "backend" })}
  ${node({ x: 312, y: 526, w: 218, h: 86, title: "Block fetchers", subtitle: "Datos agregados: estados, faltantes, acciones, fechas", kind: "data" })}
  ${node({ x: 580, y: 526, w: 218, h: 86, title: "ReportVersion", subtitle: "content_json, plan_json, llm_metadata", kind: "data" })}
  ${node({ x: 848, y: 526, w: 218, h: 86, title: "Conversation / blocks", subtitle: "Copilot, explain, regenerate, refresh-data", kind: "report" })}
  ${node({ x: 1120, y: 526, w: 218, h: 86, title: "Exports", subtitle: "ReportExport existe; render worker pendiente", kind: "data", badge: "Planeado" })}
  ${arrow({ x1: 263, y1: 161, x2: 312, y2: 161 })}
  ${arrow({ x1: 530, y1: 161, x2: 580, y2: 161 })}
  ${arrow({ x1: 798, y1: 161, x2: 848, y2: 161 })}
  ${arrow({ x1: 1066, y1: 161, x2: 1120, y2: 161 })}
  ${arrow({ x1: 957, y1: 204, x2: 421, y2: 322, label: "Generar" })}
  ${arrow({ x1: 530, y1: 365, x2: 580, y2: 365 })}
  ${arrow({ x1: 798, y1: 365, x2: 848, y2: 365 })}
  ${arrow({ x1: 1066, y1: 365, x2: 1120, y2: 365 })}
  ${arrow({ x1: 1229, y1: 408, x2: 421, y2: 526, label: "fetch data" })}
  ${arrow({ x1: 530, y1: 569, x2: 580, y2: 569 })}
  ${arrow({ x1: 798, y1: 569, x2: 848, y2: 569 })}
  ${arrow({ x1: 1066, y1: 569, x2: 1120, y2: 569, dashed: true })}
`, 720));

diagrams.set("06-data-security-flow.svg", svgShell("06 · Flujo de datos y controles de seguridad", `
  ${node({ x: 60, y: 112, w: 220, h: 90, title: "Entrada", subtitle: "JWT Bearer, cookie httpOnly o workspace token legacy", kind: "security" })}
  ${node({ x: 328, y: 112, w: 220, h: 90, title: "Guards", subtitle: "get_current_user, require_role, current_portal_workspace", kind: "security" })}
  ${node({ x: 596, y: 112, w: 220, h: 90, title: "Tenant scope", subtitle: "client_id/vendor_id desde membership o workspace", kind: "security" })}
  ${node({ x: 864, y: 112, w: 220, h: 90, title: "CORS/env", subtitle: "Origins configurables; Secure/SameSite por ambiente", kind: "security" })}
  ${node({ x: 1120, y: 112, w: 220, h: 90, title: "Errores", subtitle: "401, 403, 404, 409, 422 sin exponer datos ajenos", kind: "error" })}
  ${node({ x: 60, y: 324, w: 220, h: 90, title: "Archivo", subtitle: "PDF-only, MIME, tamaño máximo", kind: "backend" })}
  ${node({ x: 328, y: 324, w: 220, h: 90, title: "Hash", subtitle: "SHA-256, duplicate-check, storage_key", kind: "data" })}
  ${node({ x: 596, y: 324, w: 220, h: 90, title: "Storage", subtitle: "DB guarda metadatos; bytes fuera de DB", kind: "data" })}
  ${node({ x: 864, y: 324, w: 220, h: 90, title: "Prevalidación", subtitle: "pypdf, texto, encrypted/corrupt/scanned", kind: "backend" })}
  ${node({ x: 1120, y: 324, w: 220, h: 90, title: "Humano", subtitle: "IA/OCR asiste; aprobación crítica no automática", kind: "security" })}
  ${node({ x: 60, y: 536, w: 220, h: 90, title: "AuditLog", subtitle: "admin mutations, intake, reviewer decisions", kind: "data" })}
  ${node({ x: 328, y: 536, w: 220, h: 90, title: "ValidationEvent", subtitle: "timeline granular por submission/document", kind: "data" })}
  ${node({ x: 596, y: 536, w: 220, h: 90, title: "Report safety", subtitle: "snapshots, PII sanitizer, audience gates", kind: "report" })}
  ${node({ x: 864, y: 536, w: 220, h: 90, title: "Observabilidad", subtitle: "Sentry/logging/backups documentados, no cableados", kind: "security", badge: "Planeado" })}
  ${node({ x: 1120, y: 536, w: 220, h: 90, title: "Pentest/DR", subtitle: "No confirmado en repo", kind: "security", badge: "Requiere validación" })}
  ${arrow({ x1: 280, y1: 157, x2: 328, y2: 157 })}
  ${arrow({ x1: 548, y1: 157, x2: 596, y2: 157 })}
  ${arrow({ x1: 816, y1: 157, x2: 864, y2: 157 })}
  ${arrow({ x1: 1084, y1: 157, x2: 1120, y2: 157 })}
  ${arrow({ x1: 280, y1: 369, x2: 328, y2: 369 })}
  ${arrow({ x1: 548, y1: 369, x2: 596, y2: 369 })}
  ${arrow({ x1: 816, y1: 369, x2: 864, y2: 369 })}
  ${arrow({ x1: 1084, y1: 369, x2: 1120, y2: 369 })}
  ${arrow({ x1: 170, y1: 414, x2: 170, y2: 536 })}
  ${arrow({ x1: 438, y1: 414, x2: 438, y2: 536 })}
  ${arrow({ x1: 706, y1: 414, x2: 706, y2: 536 })}
`, 720));

diagrams.set("07-route-api-map.svg", svgShell("07 · Mapa de rutas frontend a APIs backend", `
  <style>.t{font-family:Inter,Arial,sans-serif;font-size:18px;font-weight:800;fill:${brand.navy}}.h{font-family:Inter,Arial,sans-serif;font-size:13px;font-weight:900;fill:${brand.white}}.c{font-family:JetBrains Mono,Consolas,monospace;font-size:13px;fill:${brand.gray950}}.m{font-family:Inter,Arial,sans-serif;font-size:12px;fill:${brand.gray600}}</style>
  <rect x="52" y="112" width="1296" height="520" rx="16" fill="#ffffff" stroke="${brand.gray200}"/>
  <rect x="52" y="112" width="1296" height="42" rx="16" fill="${brand.navy}"/>
  <text x="72" y="139" class="h">Superficie</text><text x="268" y="139" class="h">Rutas frontend</text><text x="635" y="139" class="h">Endpoints principales</text><text x="1040" y="139" class="h">Auth / estado</text>
  ${[
    ["Public", "/, /login, /activate, /admin/login", "POST /api/v1/auth/login; POST /api/v1/auth/set-password", "Public + JWT; /admin/login legacy redirect"],
    ["Proveedor", "/portal/entra-a-tu-espacio, /portal/dashboard, /portal/onboarding, /portal/upload, /portal/submissions/[id], /portal/calendar", "POST /portal/enter; GET /portal/me; GET /portal/workspaces/{id}/onboarding|dashboard|calendar|submissions/{id}; POST /portal/workspaces/{id}/submissions", "JWT owner, cookie httpOnly, X-Workspace-Token legacy"],
    ["Cliente", "/client, /client/dashboard, /client/vendors, /client/vendors/[id], /client/submissions, /client/calendar, /client/activity, /client/reports", "GET /client/me|overview|vendors|vendors/{id}|submissions|calendar|activity; /reports", "client_admin o internal_admin"],
    ["Revisor", "/admin/reviewer, /admin/reviewer/[submission_id]", "GET /reviewer/queue; GET /reviewer/submissions/{id}; POST /reviewer/submissions/{id}/decision", "reviewer o internal_admin"],
    ["Admin", "/admin, /admin/dashboard, /admin/clients, /admin/vendors, /admin/requirements, /admin/calendar, /admin/audit-log", "GET/PATCH/POST /admin/clients|vendors|workspaces|requirements; GET /admin/overview|periods|calendar|audit-log", "internal_admin"],
    ["Reportes", "/admin/reports, /client/reports, /portal/reports, /reports/[id], /print", "GET/POST/PATCH /reports; /_engine; /_presets; /from-preset; /plan; /generate; /conversation; /blocks/*", "audience gates: internal_only, client_facing, vendor_facing"],
  ].map((r, i) => {
    const y = 176 + i * 75;
    return `<g><line x1="52" y1="${y - 24}" x2="1348" y2="${y - 24}" stroke="${brand.gray100}"/>
      <text x="72" y="${y}" class="t">${esc(r[0])}</text>
      ${textBlock({ x: 268, y, text: r[1], size: 13, color: brand.gray950, weight: 700, max: 45, line: 16 })}
      ${textBlock({ x: 635, y, text: r[2], size: 12, color: brand.gray700, weight: 650, max: 55, line: 15 })}
      ${textBlock({ x: 1040, y, text: r[3], size: 12, color: brand.gray600, weight: 650, max: 34, line: 15 })}
    </g>`;
  }).join("")}
  <text x="72" y="660" class="m">Nota: todos los endpoints backend listados se sirven bajo el prefijo real /api/v1; el diagrama visual abrevia algunos nombres para legibilidad.</text>
`, 700));

diagrams.set("08-status-lifecycle.svg", svgShell("08 · Ciclo de vida de submissions/documentos", `
  ${node({ x: 50, y: 155, w: 160, h: 78, title: "pendiente", subtitle: "Sin entrega o slot faltante", kind: "data" })}
  ${node({ x: 260, y: 155, w: 160, h: 78, title: "recibido", subtitle: "Estado posible en cola", kind: "backend" })}
  ${node({ x: 470, y: 155, w: 190, h: 78, title: "pendiente_revision", subtitle: "Intake OK; espera humano", kind: "backend" })}
  ${node({ x: 710, y: 155, w: 160, h: 78, title: "prevalidado", subtitle: "Señales OK; aún humano", kind: "backend" })}
  ${node({ x: 920, y: 155, w: 190, h: 78, title: "posible_mismatch", subtitle: "Señal determinística de alerta", kind: "error" })}
  ${node({ x: 1170, y: 155, w: 170, h: 78, title: "requiere_aclaracion", subtitle: "Proveedor debe corregir", kind: "error" })}
  ${node({ x: 315, y: 390, w: 170, h: 78, title: "aprobado", subtitle: "Terminal resuelto", kind: "decision" })}
  ${node({ x: 545, y: 390, w: 170, h: 78, title: "rechazado", subtitle: "Terminal; reintento", kind: "error" })}
  ${node({ x: 775, y: 390, w: 170, h: 78, title: "excepcion_legal", subtitle: "Terminal por decisión legal", kind: "decision" })}
  ${node({ x: 1005, y: 390, w: 170, h: 78, title: "no_aplica", subtitle: "Estado canónico; sin flujo UX actual", kind: "data" })}
  ${node({ x: 50, y: 390, w: 170, h: 78, title: "vencido", subtitle: "Planeado por job temporal", kind: "error", badge: "Planeado" })}
  ${arrow({ x1: 210, y1: 194, x2: 260, y2: 194 })}
  ${arrow({ x1: 420, y1: 194, x2: 470, y2: 194 })}
  ${arrow({ x1: 660, y1: 194, x2: 710, y2: 194 })}
  ${arrow({ x1: 870, y1: 194, x2: 920, y2: 194, label: "si alerta" })}
  ${arrow({ x1: 1110, y1: 194, x2: 1170, y2: 194, label: "corregir" })}
  ${arrow({ x1: 565, y1: 233, x2: 400, y2: 390, label: "approve" })}
  ${arrow({ x1: 565, y1: 233, x2: 630, y2: 390, label: "reject" })}
  ${arrow({ x1: 805, y1: 233, x2: 860, y2: 390, label: "exception" })}
  ${arrow({ x1: 1015, y1: 233, x2: 1255, y2: 233, dashed: true, label: "reupload" })}
  ${arrow({ x1: 1255, y1: 233, x2: 1255, y2: 538, dashed: true })}
  ${arrow({ x1: 1255, y1: 538, x2: 470, y2: 538, dashed: true, label: "supersedes_submission_id" })}
  ${arrow({ x1: 470, y1: 538, x2: 470, y2: 233, dashed: true })}
  <text x="58" y="604" fill="${brand.gray600}" font-family="Inter,Arial" font-size="15">Acciones de revisor reales: approve → aprobado; reject → rechazado; request_clarification → requiere_aclaracion; mark_exception → excepcion_legal.</text>
`, 700));

for (const [name, svg] of diagrams) {
  write(path.join(diagramsDir, name), svg);
}

const routeRows = [
  ["/", "Marketing/home", "Sin API crítica", "public", "Implementado"],
  ["/login", "Login único", "POST /api/v1/auth/login", "public", "Implementado"],
  ["/activate", "Cambio forzado de password", "POST /api/v1/auth/set-password", "JWT temporal", "Parcial"],
  ["/admin/login", "Legacy redirect", "redirect a /login", "public", "Parcial"],
  ["/portal/entra-a-tu-espacio", "Confirmación de workspace", "POST /api/v1/portal/enter; GET /portal/me", "provider owner", "Implementado"],
  ["/portal/dashboard", "Dashboard proveedor", "GET /api/v1/portal/workspaces/{id}/dashboard", "portal session", "Implementado"],
  ["/portal/onboarding", "Checklist proveedor", "GET /api/v1/portal/workspaces/{id}/onboarding; POST complete-onboarding", "portal session", "Implementado"],
  ["/portal/upload", "Carga guiada", "GET /api/v1/compliance/catalog; GET /api/v1/portal/workspaces/{id}/duplicate-check; POST /api/v1/portal/workspaces/{id}/submissions", "portal session", "Implementado"],
  ["/portal/submissions/[submission_id]", "Detalle de entrega", "GET /api/v1/portal/workspaces/{id}/submissions/{submission_id}", "portal session", "Implementado"],
  ["/portal/calendar", "Calendario proveedor", "GET /api/v1/portal/workspaces/{id}/calendar", "portal session", "Implementado"],
  ["/portal/reports", "Reportes proveedor", "GET /api/v1/reports; GET /api/v1/reports/_presets; POST /api/v1/reports/from-preset", "vendor_facing", "Parcial"],
  ["/portal/reports/[id]", "Editor reporte proveedor", "GET/PATCH/POST /api/v1/reports/*", "vendor_facing", "Parcial"],
  ["/portal/reports/[id]/print", "Vista imprimible proveedor", "GET /api/v1/reports/{report_id}", "vendor_facing", "Parcial"],
  ["/client", "Redirect cliente", "redirect a /client/dashboard", "client_admin", "Implementado"],
  ["/client/dashboard", "Dashboard cliente", "GET /api/v1/client/overview", "client_admin/internal_admin", "Implementado"],
  ["/client/vendors", "Proveedores cliente", "GET /api/v1/client/vendors", "client_admin/internal_admin", "Implementado"],
  ["/client/vendors/[vendor_id]", "Detalle proveedor", "GET /api/v1/client/vendors/{vendor_id}", "client_admin/internal_admin", "Implementado"],
  ["/client/submissions", "Entregas cliente", "GET /api/v1/client/submissions", "client_admin/internal_admin", "Implementado"],
  ["/client/calendar", "Calendario cliente", "GET /api/v1/client/calendar", "client_admin/internal_admin", "Implementado"],
  ["/client/activity", "Actividad cliente", "GET /api/v1/client/activity", "client_admin/internal_admin", "Implementado"],
  ["/client/reports", "Reportes cliente", "GET /api/v1/reports; POST /api/v1/reports/from-preset", "client_facing", "Implementado"],
  ["/client/reports/[id]", "Editor reporte cliente", "GET/PATCH/POST /api/v1/reports/*", "client_facing", "Implementado"],
  ["/admin", "Landing interna", "GET /api/v1/auth/me; navegación admin", "staff", "Implementado"],
  ["/admin/dashboard", "Dashboard admin", "GET /api/v1/admin/overview", "internal_admin", "Implementado"],
  ["/admin/reviewer", "Queue revisión", "GET /api/v1/reviewer/queue", "reviewer/internal_admin", "Implementado"],
  ["/admin/reviewer/[submission_id]", "Detalle revisión", "GET /api/v1/reviewer/submissions/{id}; POST /api/v1/reviewer/submissions/{id}/decision", "reviewer/internal_admin", "Implementado"],
  ["/admin/clients", "Clientes", "GET/POST/PATCH /api/v1/admin/clients", "internal_admin", "Implementado"],
  ["/admin/vendors", "Proveedores", "GET/POST/PATCH /api/v1/admin/vendors", "internal_admin", "Implementado"],
  ["/admin/requirements", "Catálogo requisitos", "GET/POST/PATCH /api/v1/admin/requirements", "internal_admin", "Implementado"],
  ["/admin/calendar", "Calendario admin", "GET /api/v1/admin/calendar; GET /api/v1/admin/periods", "internal_admin", "Implementado"],
  ["/admin/audit-log", "Bitácora", "GET /api/v1/admin/audit-log", "internal_admin", "Implementado"],
  ["/admin/reports", "Reportes internos", "GET /api/v1/reports; GET /api/v1/reports/_presets; POST /api/v1/reports/from-preset", "internal/reviewer", "Implementado"],
  ["/admin/reports/[id]", "Editor reporte interno", "GET/PATCH/POST /api/v1/reports/*", "internal/reviewer", "Implementado"],
];

const maturityRows = [
  ["Frontend routes", "Implementado", "frontend/app/**/page.tsx; route_inventory.csv", "Algunas rutas reportes proveedor bloqueadas por datos/DB", "Cerrar provider reports y activar pruebas con ids propios"],
  ["Backend APIs", "Implementado", "backend/app/api/v1/*.py; API_CONTRACT_MAP.md", "Superficie amplia; no endpoint de descarga de documentos", "Agregar descarga segura/presigned URL con RBAC"],
  ["Upload workflow", "Implementado", "portal.py create_workspace_submission; submission_service.py", "Legacy /submissions aún existe y confía identidad de formulario", "Mantener solo para importer/dev; migrar wizard a catálogo workspace-scoped"],
  ["Reports", "Parcial", "reports.py, report_service.py, executor.py, REPORTS_AUDIT_2026-05-18.md", "Mock LLM si no hay ANTHROPIC_API_KEY; exports async pendientes", "Configurar AI real, completar export worker y provider report creation"],
  ["Auth/security", "Parcial", "auth.py, portal_session.py, config.py", "Activation cancel bug; portal token legacy; producción no validada", "Fix /activate cancel, retirar legacy token gradualmente, hardening prod"],
  ["Database/migrations", "Implementado", "alembic/versions/0001-0009; models/entities.py", "Faltan tablas futuras de sharing/export worker completas según docs", "Aplicar/validar migraciones en staging"],
  ["Document storage", "Parcial", "storage.py; .env.example", "S3/R2 soportado en código, requiere credenciales y prueba de operación", "Configurar bucket, TTL, backups y pruebas de restore"],
  ["AI/LLM", "Parcial", "llm/factory.py; planner.py; executor.py", "Asistente, no autoridad legal; fallback mock puede confundir si no se mira banner", "Definir policy de uso, logs y evaluación de calidad"],
  ["Deployment config", "Requiere validación", "render.yaml; .env.example; PROD_AUDIT_2026-05-18.md", "Secrets, CORS, storage, observabilidad y backups requieren staging real", "Checklist prod + smoke tests end-to-end"],
  ["Design system", "Implementado", "globals.css; docs/DESIGN_SYSTEM.md; brand assets", "Algunas pantallas aún pueden requerir pulido UX", "Continuar redesign guiado por datos reales"],
  ["Testing", "Implementado", "backend/tests; QA_RESULTS.md", "No se corrieron tests en este build documental; frontend E2E limitado a auditorías previas", "Añadir Playwright E2E para rutas críticas"],
];

function badge(label) {
  const tone = statusTone[label] || statusTone.Implementado;
  return `<span class="badge" style="background:${tone.bg};border-color:${tone.border};color:${tone.fg}">${esc(label)}</span>`;
}

function table(headers, rows, className = "") {
  return `<table class="${className}"><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows
    .map((r) => `<tr>${r.map((c, i) => `<td>${i === r.length - 1 && statusTone[c] ? badge(c) : esc(c)}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

function diagram(name, alt) {
  return `<img class="diagram-img" src="diagrams/${name}" alt="${esc(alt)}">`;
}

const html = `<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CheckWise — Mapa Final del Flujo del Sistema</title>
<style>
  @page { size: A3 landscape; margin: 0; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #dfe7ef; color: ${brand.gray950}; font-family: Inter, "Open Sans", Arial, sans-serif; }
  .page { width: 420mm; height: 297mm; padding: 20mm 22mm; background: #fff; page-break-after: always; position: relative; overflow: hidden; }
  .page:last-child { page-break-after: auto; }
  .cover { background: linear-gradient(90deg, ${brand.navy} 0%, #02324f 62%, #f7f9fb 62%); color: #fff; }
  .cover h1 { font-size: 60px; line-height: .98; margin: 58mm 0 8mm; letter-spacing: 0; width: 56%; }
  .cover .sub { font-size: 24px; line-height: 1.35; width: 58%; color: #d8eef5; }
  .cover .meta { position: absolute; bottom: 28mm; left: 22mm; font-size: 15px; line-height: 1.8; color: #d8eef5; }
  .cover .panel { position: absolute; right: 22mm; top: 28mm; width: 120mm; height: 236mm; color: ${brand.gray950}; padding: 16mm; border-left: 4px solid ${brand.teal}; }
  .logo { height: 15mm; background: white; padding: 3mm 5mm; border: 1px solid ${brand.gray200}; }
  h2 { margin: 0 0 5mm; color: ${brand.navy}; font-size: 34px; line-height: 1.08; letter-spacing: 0; }
  h3 { margin: 0 0 4mm; color: ${brand.navy}; font-size: 19px; }
  .eyebrow { color: ${brand.tealDark}; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; font-size: 12px; margin-bottom: 4mm; }
  .lead { font-size: 17px; color: ${brand.gray600}; line-height: 1.45; max-width: 330mm; margin-bottom: 8mm; }
  .footer { position: absolute; left: 22mm; right: 22mm; bottom: 10mm; border-top: 1px solid ${brand.gray200}; padding-top: 4mm; display: flex; justify-content: space-between; color: ${brand.gray500}; font-size: 10px; font-weight: 700; }
  .diagram-img { width: 100%; max-height: 205mm; object-fit: contain; display: block; border: 1px solid ${brand.gray200}; border-radius: 8px; background: #fff; }
  .grid { display: grid; gap: 6mm; }
  .cols-2 { grid-template-columns: 1fr 1fr; }
  .cols-3 { grid-template-columns: repeat(3, 1fr); }
  .card { border: 1px solid ${brand.gray200}; border-top: 3px solid ${brand.navy}; border-radius: 8px; padding: 6mm; background: #fff; box-shadow: 0 6px 22px rgba(1,53,87,.07); }
  .card.teal { border-top-color: ${brand.teal}; }
  .card.warn { border-top-color: #b87500; background: #fffaf0; }
  .card.err { border-top-color: ${brand.red}; background: #fff7f7; }
  .card p, li { font-size: 13px; line-height: 1.38; color: ${brand.gray700}; }
  ul { padding-left: 18px; margin: 2mm 0 0; }
  code { font-family: "JetBrains Mono", Consolas, monospace; color: ${brand.navy}; font-size: .92em; }
  .legend { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4mm; }
  .legend-item { border: 1px solid ${brand.gray200}; border-radius: 8px; padding: 4mm; font-size: 13px; display: flex; align-items: center; gap: 3mm; min-height: 18mm; }
  .swatch { width: 16px; height: 16px; border-radius: 4px; border: 2px solid ${brand.gray300}; flex: 0 0 auto; }
  table { width: 100%; border-collapse: collapse; font-size: 10.4px; table-layout: fixed; }
  th { background: ${brand.navy}; color: #fff; text-align: left; padding: 8px; font-size: 10px; }
  td { border-bottom: 1px solid ${brand.gray200}; padding: 7px 8px; vertical-align: top; color: ${brand.gray700}; overflow-wrap: anywhere; }
  tbody tr:nth-child(even) td { background: ${brand.gray50}; }
  .route-table th:nth-child(1), .route-table td:nth-child(1) { width: 20%; font-family: "JetBrains Mono", Consolas, monospace; color: ${brand.navy}; }
  .route-table th:nth-child(2), .route-table td:nth-child(2) { width: 17%; }
  .route-table th:nth-child(3), .route-table td:nth-child(3) { width: 34%; font-family: "JetBrains Mono", Consolas, monospace; font-size: 9.5px; }
  .route-table th:nth-child(4), .route-table td:nth-child(4) { width: 17%; }
  .route-table th:nth-child(5), .route-table td:nth-child(5) { width: 12%; }
  .maturity th:nth-child(1), .maturity td:nth-child(1) { width: 17%; font-weight: 800; color: ${brand.navy}; }
  .maturity th:nth-child(2), .maturity td:nth-child(2) { width: 13%; }
  .maturity th:nth-child(3), .maturity td:nth-child(3) { width: 25%; font-family: "JetBrains Mono", Consolas, monospace; font-size: 9.7px; }
  .maturity th:nth-child(4), .maturity td:nth-child(4) { width: 22%; }
  .maturity th:nth-child(5), .maturity td:nth-child(5) { width: 23%; }
  .badge { display: inline-block; border: 1px solid; border-radius: 999px; padding: 3px 8px; font-size: 9px; line-height: 1; font-weight: 900; white-space: nowrap; }
  .note { border-left: 4px solid ${brand.teal}; background: #effdfb; padding: 5mm 6mm; color: ${brand.gray700}; font-size: 14px; line-height: 1.45; }
  .small { font-size: 11px; color: ${brand.gray500}; line-height: 1.35; }
  .wall { display: grid; grid-template-columns: 62% 38%; gap: 7mm; align-items: start; }
  .mini-lifecycle { display: flex; gap: 2mm; flex-wrap: wrap; }
  .pill { border: 1px solid ${brand.gray200}; border-radius: 999px; padding: 2.5mm 3.5mm; font-size: 11px; font-family: "JetBrains Mono", Consolas, monospace; background: ${brand.gray50}; color: ${brand.navy}; }
</style>
</head>
<body>
<section class="page cover">
  <img class="logo" src="../../frontend/public/checkwise-logo.png" alt="CheckWise logo">
  <h1>CheckWise<br>Mapa Final<br>del Flujo del Sistema</h1>
  <p class="sub">Flujos, rutas, redirecciones, APIs, estados documentales y controles de seguridad.</p>
  <div class="meta">
    Preparado para alineación técnica y de producto<br>
    Owner: Jose Pablo Samano<br>
    Fecha: ${DATE}
  </div>
  <div class="panel">
    <h3>Alcance del documento</h3>
    <p>Referencia técnica imprimible para entender cómo CheckWise mueve evidencia REPSE desde proveedor hasta revisión, reporte y auditoría.</p>
    <p>Basado en archivos reales del repo: <code>frontend/app</code>, <code>backend/app</code>, <code>docs/API_CONTRACT_MAP.md</code>, <code>docs/DATA_MODEL.md</code>, auditorías de rutas y reportes.</p>
    <p><strong>No es marketing.</strong> Cuando algo no está completo se etiqueta como parcial, planeado, faltante o por validar.</p>
  </div>
</section>

<section class="page">
  <div class="eyebrow">Sección 2</div>
  <h2>Leyenda y guía de lectura</h2>
  <p class="lead">Cada flecha representa una transición accionable: una navegación frontend, una llamada HTTP, un write en base de datos, una validación o un redirect. Los nombres técnicos se mantienen en su forma original.</p>
  <div class="legend">
    <div class="legend-item"><span class="swatch" style="background:#eef9f7;border-color:${brand.teal}"></span><strong>Usuario / actor</strong></div>
    <div class="legend-item"><span class="swatch" style="background:#eff6fb;border-color:${brand.navy3}"></span><strong>Frontend route/page</strong></div>
    <div class="legend-item"><span class="swatch" style="background:#fff7e6;border-color:#b87500"></span><strong>Backend API / proceso</strong></div>
    <div class="legend-item"><span class="swatch" style="background:#f7f9fb;border-color:${brand.gray300}"></span><strong>DB / storage</strong></div>
    <div class="legend-item"><span class="swatch" style="background:#fff0f0;border-color:${brand.red}"></span><strong>Seguridad / error</strong></div>
    <div class="legend-item"><span class="swatch" style="background:#edf6ff;border-color:${brand.blue}"></span><strong>Reportes / IA</strong></div>
    <div class="legend-item"><span class="swatch" style="background:#fff;border-color:${brand.teal}"></span><strong>Decisión / estado</strong></div>
    <div class="legend-item"><span class="swatch" style="background:repeating-linear-gradient(90deg,#fff,#fff 5px,#dde2ec 5px,#dde2ec 10px)"></span><strong>Futuro / excepción</strong></div>
  </div>
  <div class="grid cols-3" style="margin-top:9mm">
    <div class="card"><h3>Etiquetas de madurez</h3><p>${badge("Implementado")} existe en código y está conectado.</p><p>${badge("Parcial")} existe con limitaciones, mocks o casos no cerrados.</p><p>${badge("Planeado")} hay modelo, documento o esqueleto técnico, pero falta ejecución.</p></div>
    <div class="card teal"><h3>Cómo leer rutas</h3><p><code>/portal/upload</code> es la ruta visible. <code>POST /api/v1/portal/workspaces/{id}/submissions</code> es el backend que procesa el upload. El PDF conserva los nombres exactos.</p></div>
    <div class="card warn"><h3>Regla de honestidad</h3><p>Si algo aparece en documentación pero no en código, se marca como documentado/no completo. Si el código existe pero requiere staging, se marca por validar.</p></div>
  </div>
  <div class="footer"><span>CHECKWISE · SYSTEM WORKFLOW MAP</span><span>02</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 3</div><h2>Vista general completa del sistema</h2>
  <p class="lead">El producto opera tres rutas principales: proveedor, cliente y equipo interno. El backend mantiene la verdad documental: estados, eventos, hashes, inspección PDF, auditoría y reportes.</p>
  ${diagram("01-system-overview.svg", "Vista general")}
  <div class="footer"><span>Fuente: ARCHITECTURE.md, DATA_MODEL.md, backend/app/models/entities.py</span><span>03</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 4</div><h2>Autenticación, entrada y redirecciones</h2>
  <p class="lead">CheckWise centralizó login en <code>/login</code>. Staff y clientes usan JWT con roles; proveedor entra al portal mediante workspace propio y cookie httpOnly. El token legacy de workspace todavía existe como transición.</p>
  ${diagram("02-auth-and-entry-flow.svg", "Auth y redirects")}
  <div class="grid cols-2" style="margin-top:5mm">
    <div class="note">Redirects confirmados: admin → <code>/admin/reviewer</code>, client_admin → <code>/client/dashboard</code>, provider → <code>/portal/entra-a-tu-espacio</code>, must_change_password → <code>/activate</code>.</div>
    <div class="note" style="border-left-color:${brand.red};background:#fff7f7">Riesgo vigente: <code>/activate</code> cancelar puede conservar JWT temporal; documentado como FAIL/P1 en <code>redirect_matrix.csv</code>.</div>
  </div>
  <div class="footer"><span>Fuente: app/login/page.tsx, auth.py, portal.py, redirect_matrix.csv</span><span>04</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 5</div><h2>Proveedor: onboarding y carga documental</h2>
  <p class="lead">La ruta segura de upload deriva identidad desde <code>ProviderWorkspace</code>. El navegador no decide cliente/proveedor/contrato; el backend lo resuelve desde la sesión.</p>
  ${diagram("03-supplier-upload-flow.svg", "Supplier upload")}
  <div class="footer"><span>Fuente: portal.py, submission_service.py, storage.py, pdf_validation.py, prevalidation.py</span><span>05</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 6</div><h2>Revisión interna/legal y transición de estados</h2>
  <p class="lead">La revisión crítica es humana. Las señales automáticas ayudan a priorizar, pero la aprobación no se automatiza. Cada decisión escribe estado, historial, evento y auditoría.</p>
  ${diagram("04-internal-review-flow.svg", "Internal review")}
  <div class="footer"><span>Fuente: reviewer.py, submission_workflow.py, constants/statuses.py</span><span>06</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 7</div><h2>Reportes: de datos operativos a insight ejecutivo</h2>
  <p class="lead">Reportes no es solo exportar. El sistema crea reportes versionados desde scopes autorizados, snapshots de cumplimiento y bloques renderizados. La IA puede planear y redactar, pero el backend filtra datos y audiencias.</p>
  ${diagram("05-reporting-flow.svg", "Reporting flow")}
  <div class="grid cols-3" style="margin-top:5mm">
    <div class="card"><h3>Implementado</h3><p>CRUD de reportes, presets, versiones, planner, generate SSE, conversation, explain/regenerate/refresh-data.</p></div>
    <div class="card warn"><h3>Parcial</h3><p>Si no hay <code>ANTHROPIC_API_KEY</code>, usa <code>DeterministicMockLLMClient</code>. El editor muestra banner via <code>/_engine</code>.</p></div>
    <div class="card err"><h3>Limitación</h3><p>Exports asíncronos existen en modelo, pero el worker de render todavía está planeado. Provider reports tiene bloqueo 403 en DB actual según auditoría.</p></div>
  </div>
  <div class="footer"><span>Fuente: REPORTS_ARCHITECTURE.md, REPORTS_AUDIT_2026-05-18.md, reports.py, executor.py</span><span>07</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 8</div><h2>Modelo de datos y ciclo de vida documental</h2>
  <div class="grid cols-2">
    <div>
      ${diagram("08-status-lifecycle.svg", "Status lifecycle")}
    </div>
    <div class="card">
      <h3>Entidades principales</h3>
      <p><code>Client</code> → <code>Vendor</code> → <code>Contract</code> → <code>ProviderWorkspace</code> definen identidad y alcance.</p>
      <p><code>Period</code>, <code>Institution</code>, <code>Requirement</code>, <code>RequirementVersion</code> definen el marco regulatorio versionado.</p>
      <p><code>Submission</code> une cliente, proveedor, contrato, periodo, institución, requisito, estado y lineage.</p>
      <p><code>Document</code> guarda metadata del archivo: <code>storage_key</code>, <code>sha256</code>, MIME, tamaño y <code>ocr_status</code>.</p>
      <p><code>Validation</code>, <code>ValidationEvent</code>, <code>DocumentInspection</code>, <code>DocumentStatusHistory</code> y <code>AuditLog</code> dan trazabilidad.</p>
      <p><code>Report</code>, <code>ReportVersion</code>, <code>ReportConversation</code>, <code>ComplianceSnapshot</code>, <code>ReportShare</code>, <code>ReportExport</code> soportan reporting versionado.</p>
    </div>
  </div>
  <div class="footer"><span>Fuente: DATA_MODEL.md, entities.py, statuses.py</span><span>08</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 9</div><h2>Route-to-API map visual</h2>
  <p class="lead">Mapa comprimido por superficie. La tabla completa de rutas aparece en la siguiente página para trazabilidad operativa.</p>
  ${diagram("07-route-api-map.svg", "Route API map")}
  <div class="footer"><span>Fuente: frontend/app inventory, backend/app/api/v1 inventory</span><span>09</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 9 · detalle</div><h2>Tabla route-to-API</h2>
  ${table(["Ruta frontend", "Propósito", "Endpoint(s) backend", "Auth/rol", "Estado"], routeRows.slice(0, 22), "route-table")}
  <div class="footer"><span>Fuente: frontend/app/**/*.tsx, frontend/lib/api/*.ts, backend/app/api/v1/*.py</span><span>10</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 9 · detalle</div><h2>Tabla route-to-API · continuación</h2>
  ${table(["Ruta frontend", "Propósito", "Endpoint(s) backend", "Auth/rol", "Estado"], routeRows.slice(22), "route-table")}
  <div class="note" style="margin-top:8mm">La tabla distingue rutas implementadas de superficies parciales. En particular, las rutas de reportes para proveedor existen en frontend/backend, pero la auditoría actual documenta bloqueo 403 para creación/apertura con la base de datos vigente.</div>
  <div class="footer"><span>Fuente: route_inventory.csv, redirect_matrix.csv, API_CONTRACT_MAP.md</span><span>11</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 10</div><h2>Controles de seguridad y ciberseguridad</h2>
  <p class="lead">Los controles existen por capas: entrada, scope, archivo, storage, auditoría y reportes. Algunos ya son código operativo; otros requieren validación productiva.</p>
  ${diagram("06-data-security-flow.svg", "Security flow")}
  <div class="grid cols-3" style="margin-top:5mm">
    <div class="card"><h3>${badge("Implementado")} Código</h3><p>JWT HS256, bcrypt, roles/memberships, CORS configurable, PDF-only, size cap, SHA-256, AuditLog, ValidationEvent, tenant-safe workspace upload.</p></div>
    <div class="card warn"><h3>${badge("Parcial")} Producción</h3><p>S3/R2 soportado por <code>storage.py</code>, pero necesita bucket, secrets, backup/restore y smoke tests reales.</p></div>
    <div class="card err"><h3>${badge("Faltante recomendado")} Hardening</h3><p>Pentest externo, observabilidad, descarga segura de documentos, membership editor, correcciones backend, notificaciones y DR.</p></div>
  </div>
  <div class="footer"><span>Fuente: auth.py, config.py, storage.py, API_CONTRACT_MAP.md, PROD_AUDIT_2026-05-18.md</span><span>12</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 11</div><h2>Estado actual de implementación</h2>
  ${table(["Área", "Estado", "Evidencia del repo", "Riesgo", "Siguiente acción recomendada"], maturityRows, "maturity")}
  <div class="footer"><span>Fuente: auditorías, tests, docs y código actual</span><span>13</span></div>
</section>

<section class="page">
  <div class="eyebrow">Sección 12</div><h2>Wall map: flujo completo de oficina</h2>
  <p class="lead">Referencia rápida para imprimir: usuario → ruta → API → dato → estado → reporte → seguridad.</p>
  <div class="wall">
    <div>
      ${diagram("01-system-overview.svg", "Wall overview")}
      <div style="margin-top:5mm">${diagram("03-supplier-upload-flow.svg", "Wall upload")}</div>
    </div>
    <div class="grid">
      <div class="card teal"><h3>Happy path</h3><p>Proveedor entra por <code>/login</code> → <code>/portal/entra-a-tu-espacio</code> → dashboard/onboarding → upload → backend guarda PDF y metadata → revisión humana → estado visible para portal/cliente/reportes.</p></div>
      <div class="card"><h3>Estados clave</h3><div class="mini-lifecycle">${["pendiente","pendiente_revision","prevalidado","posible_mismatch","aprobado","rechazado","requiere_aclaracion","excepcion_legal"].map(s => `<span class="pill">${s}</span>`).join("")}</div></div>
      <div class="card warn"><h3>Checkpoints críticos</h3><ul><li>JWT/role o portal session antes de leer datos.</li><li>Tenant identity siempre desde workspace/membership.</li><li>PDF-only + size + SHA-256 antes de persistir metadata.</li><li>AuditLog y ValidationEvent en intake y decisiones.</li><li>IA como asistente; revisión humana conserva autoridad.</li></ul></div>
      <div class="card err"><h3>Brechas prioritarias</h3><ul><li>Fix <code>/activate</code> cancel/JWT temporal.</li><li>Cerrar provider reports 403 en DB actual.</li><li>Agregar descarga segura de documentos.</li><li>Completar backend de correcciones/notificaciones.</li><li>Validar S3/R2, observabilidad, backups y CORS producción.</li></ul></div>
    </div>
  </div>
  <div class="footer"><span>CHECKWISE · OFFICE WALL REFERENCE</span><span>14</span></div>
</section>
</body>
</html>`;

write(path.join(outDir, "checkwise-final-system-workflow.html"), html);

const readme = `# CheckWise — Mapa Final del Flujo del Sistema

Fecha: ${DATE}

## Archivos creados

- \`checkwise-final-system-workflow.pdf\` — PDF final imprimible en A3 horizontal.
- \`checkwise-final-system-workflow.html\` — fuente HTML/CSS usado para renderizar el PDF.
- \`diagrams/*.svg\` — diagramas reutilizables como assets independientes.
- \`scripts/build-system-workflow-map.mjs\` — script generador.

## Diagramas creados

1. \`01-system-overview.svg\` — vista general end-to-end.
2. \`02-auth-and-entry-flow.svg\` — autenticación, entrada y redirects.
3. \`03-supplier-upload-flow.svg\` — onboarding y upload del proveedor.
4. \`04-internal-review-flow.svg\` — revisión interna/legal.
5. \`05-reporting-flow.svg\` — reportes y asistencia IA.
6. \`06-data-security-flow.svg\` — datos y controles de seguridad.
7. \`07-route-api-map.svg\` — mapa de rutas a APIs.
8. \`08-status-lifecycle.svg\` — ciclo de vida de estados.

## Inspección realizada

- Frontend: \`frontend/app/**/*.tsx\`, \`frontend/lib/api/*.ts\`, session guards y redirects.
- Backend: \`backend/app/api/v1/*.py\`, \`backend/app/services/*.py\`, modelos, constantes y configuración.
- Docs: \`API_CONTRACT_MAP.md\`, \`ARCHITECTURE.md\`, \`DATA_MODEL.md\`, \`REPORTS_ARCHITECTURE.md\`, \`REPORTS_AUDIT_2026-05-18.md\`, \`codex-route-workflow-audit/*\`, \`PROD_AUDIT_2026-05-18.md\`.
- Brand: \`frontend/app/globals.css\`, \`docs/DESIGN_SYSTEM.md\`, \`frontend/public/checkwise-logo.png\`.

## Supuestos y límites

- El PDF distingue entre implementado, parcial, planeado, requiere validación y faltante recomendado.
- No se afirma producción endurecida. Storage S3/R2, observabilidad, backups, pentest y CORS producción requieren validación real.
- IA/LLM se presenta como asistencia. Si \`ANTHROPIC_API_KEY\` no existe, el backend usa mock determinístico.
- \`POST /api/v1/submissions\` se marca como legacy/deprecated; el flujo recomendado es \`POST /api/v1/portal/workspaces/{id}/submissions\`.
- Provider reports se marca parcial porque la auditoría de rutas documenta bloqueo 403 en la DB actual.

## Workflows inconsistentes o faltantes destacados

- \`/activate\`: cancelar puede conservar JWT temporal y enviar al portal sin cambio de password.
- \`/admin/login\`: redirect legacy a \`/login\` causa double-hop cosmético.
- No existe endpoint final de descarga segura de documentos para cliente/admin.
- No existe backend real para correcciones de workspace/contact requests/notificaciones.
- Exports async de reportes tienen modelo \`ReportExport\`, pero falta worker/render productivo.
`;

write(path.join(outDir, "README.md"), readme);

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1587, height: 1122 }, deviceScaleFactor: 1 });
await page.goto(`file://${path.join(outDir, "checkwise-final-system-workflow.html")}`, { waitUntil: "networkidle" });
await page.emulateMedia({ media: "print" });
await page.pdf({
  path: path.join(outDir, "checkwise-final-system-workflow.pdf"),
  format: "A3",
  landscape: true,
  printBackground: true,
  preferCSSPageSize: true,
});
await browser.close();

console.log(JSON.stringify({
  pdf: path.join(outDir, "checkwise-final-system-workflow.pdf"),
  html: path.join(outDir, "checkwise-final-system-workflow.html"),
  diagrams: [...diagrams.keys()].map((n) => path.join(diagramsDir, n)),
}, null, 2));
