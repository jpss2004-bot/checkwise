# Flagship Demo — Sales Walkthrough Script

A ~10-minute narrated path that tells the CheckWise story end-to-end. Two logins (client + provider). Mexican Spanish UI. Credentials in `RUNBOOK.md`.

**The story in one line:** "Here's a 92%-compliant supplier portfolio — strong overall, but CheckWise instantly surfaces the *one* provider putting you at risk, lets you act on it, and proves it all to an auditor."

---

## Act 1 — The Client sees the whole portfolio at a glance (3 min)

**1. Log in** → `demo.cliente@checkwise.mx`. Lands on **`/client/dashboard`**.
> "This is what your compliance lead sees every morning."

**2. The headline.** Point at the **92% donut** and "**Tienes 1 proveedor en riesgo**."
> "92% of your REPSE obligations across 5 providers are in order — and CheckWise is already telling you exactly where the risk is: one provider. You're not hunting through folders."

**3. Portfolio signals.** Walk the buckets: *Faltantes obligatorios*, *En revisión por nuestro equipo*, *Por vencer ≤14 días*, and the **Al día / En proceso / En riesgo** ring (1 / 3 / 1).
> "Every number is live — computed from the actual documents, not a static slide."

**4. Provider portfolio** → **`/client/vendors`**. Show the five providers, each with a semáforo and a % bar:
| Provider | | |
|---|---|---|
| Grupo Industrial Vallejo | 🟢 100% | "your model supplier" |
| Servicios Logísticos Anáhuac | 🟡 98% | "strong; a renewal coming up" |
| Mantenimiento y Limpieza Tlalpan | 🟡 88% | "average; a few gaps" |
| Constructora del Bajío | 🟡 91% | "improving fast" |
| **Transportes y Distribución del Golfo** | 🔴 **83%** | **"the one to worry about"** |

---

## Act 2 — Investigate the problem provider (3 min)

**5. Open Transportes y Distribución del Golfo** (the red one).
> "CheckWise doesn't just say 'red' — it shows you *why*."
Point at the signals: **CSF vencida** (expired tax certificate), **REPSE rechazado** (rejected registration), **rejected filings**, **open aclaraciones** (corrective actions), **RFC mismatches**, **missing recent obligations**.

**6. Open a document.** Click the provider's **CSF** → it opens as a real PDF with a red **"VENCIDO"** watermark.
> "This is the actual evidence on file — and CheckWise flagged it as expired automatically. Open any document: contracts, REPSE registrations, tax constancias — they're all here, organized by institution and period."

**7. Reports** → **`/client/reports`**. Open:
- **Resumen ejecutivo mensual** — the one-page exec view.
- **Matriz de riesgo de proveedores** — providers ranked by risk.
- **Evidencia faltante del portafolio** — exactly what's missing, by provider.
> "Board-ready in seconds, generated from live data."

**8. Audit package** → back on **`/client/vendors`**, click **"Preparar paquete para auditoría."**
> "When an auditor shows up, you hand them this — a single ZIP, organized by provider → institution → period, with an index. Hundreds of documents, already assembled."

**9. The point.** 
> "In two minutes you saw a strong 92% portfolio, found the one provider creating risk, opened the evidence, and produced an audit package. That's the visibility you don't have today."

---

## Act 3 — The Provider side: close the loop (3 min)

**10. Switch accounts** → log out, log in as `demo.proveedor@checkwise.mx` (this is **Constructora del Bajío**, the improving provider). Lands on **`/portal`**.
> "Now you're the supplier. This is what *they* see — no training required."

**11. Upload documents.** Their calendar shows a few **obligations still pending** (missing recent months). Upload one (drag a PDF).
> "The provider uploads directly. No email chains, no chasing."

**12. Respond to observations.** Show an item with a reviewer note; demonstrate re-uploading to resolve it.
> "When your team requests a correction, the provider sees exactly what's needed and responds in place."

**13. Back to the Client** → log back in as `demo.cliente@checkwise.mx`, open Constructora del Bajío.
> "The obligations you just uploaded now read **'En revisión'** instead of **'Faltante'** — the gap is closing in real time."

**14. See the improvement.** The provider's faltantes count has dropped; the portfolio is trending up.
> "Once your compliance team approves them, that provider goes green. That's the whole loop — visibility, action, proof — in one platform, from both sides."

---

## Quick-reference cheat sheet

| Beat | Route | What to show |
|---|---|---|
| Strong portfolio | `/client/dashboard` | 92% donut, "1 en riesgo", buckets |
| Provider spread | `/client/vendors` | 1🟢 / 3🟡 / 1🔴, % bars |
| Problem provider | open *Transportes del Golfo* | expired CSF, rejected REPSE, aclaraciones |
| Real evidence | open a document | branded PDF; VENCIDO watermark on E's CSF |
| Reports | `/client/reports` | 3 reports, live data |
| Audit package | `/client/vendors` → "Preparar paquete" | ZIP across 5 providers |
| Provider side | `/portal` (provider login) | upload, observations, calendar |
| Close the loop | back to client view | Faltante → En revisión |

**If asked "is this real data?"** — "It's a demonstration portfolio with fictional companies, but every number, semáforo, report and audit package is produced by the exact same engine your production tenant would use. Nothing here is mocked up for the slide."
