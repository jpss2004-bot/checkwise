# XML Upload Security Recommendation

**Status:** decision recorded.
**Last reviewed:** 2026-05-20 (Stage 2.5).
**Companion docs:** [../audits/provider-feedback-transcript/PROVIDER_TRANSCRIPT_FEEDBACK_MAP.md](../audits/provider-feedback-transcript/PROVIDER_TRANSCRIPT_FEEDBACK_MAP.md) (theme T6).

---

## 1. Decision

**Block XML uploads by default. Do not enable XML acceptance without a documented, scoped, security-reviewed change.**

This document records the current stance, the layers that enforce it, the threats XML uploads would introduce, and the conditions that would have to hold before reopening the question.

---

## 2. Current enforcement (verified 2026-05-20)

CheckWise rejects non-PDF uploads at three independent layers:

1. **Configuration default.**
   `backend/app/core/config.py:37`
   ```python
   ALLOWED_FILE_EXTENSIONS: str = ".pdf"
   ```
   The setting reads from `CHECKWISE_ALLOWED_FILE_EXTENSIONS` env if present, but the shipped default is PDF-only. The exposed property `allowed_extensions_set` splits the string on commas, so adding `.xml` would require an intentional config change in every deployment environment.

2. **Submission-service hard check.**
   `backend/app/services/submission_service.py:57`
   ```python
   if not filename.lower().endswith(".pdf"):
       ...
   ```
   The portal's `POST /api/v1/portal/workspaces/{id}/submissions` calls `assert_pdf_upload(file)` (line 1495) before any storage write. Any file with a non-`.pdf` extension is rejected with HTTP 422 + plain-Spanish detail before reaching disk.

3. **Prevalidation `allowed_file_type` rule.**
   `backend/app/services/prevalidation.py:30`
   ```python
   allowed_type = stored_file.extension in settings.allowed_extensions_set
   ```
   The validation pipeline records a `fail` signal on any extension outside `allowed_extensions_set`. Even if a future config change loosened the extension set, the rule would still flag the document for human review.

The dry-run metadata endpoint at `backend/app/api/v1/metadata_dry_run.py:41` also gates on `.pdf` before storing the file.

**Net effect:** today, an attacker (or a curious provider) cannot upload an XML file through any public CheckWise endpoint. The blocking happens at the configuration level, the service-layer hard check, and the prevalidation rule.

---

## 3. Threat model if XML were enabled naively

If `ALLOWED_FILE_EXTENSIONS` were changed to `.pdf,.xml` without further hardening, CheckWise would be exposed to the canonical XML-parser attack surface:

| Threat | Description | Severity |
|---|---|---|
| **XML External Entity (XXE)** | A malicious XML uses `<!ENTITY` to read arbitrary files from disk (`/etc/passwd`, app secrets, S3 credentials) or to call out to internal services. Reference: OWASP XXE Prevention Cheat Sheet. | Critical |
| **Billion-laughs / quadratic blowup** | Nested entities cause exponential expansion → memory exhaustion + denial of service. | High |
| **XSLT injection** | A `<?xml-stylesheet ?>` reference to attacker-controlled XSL triggers code execution under the parser. | High |
| **Schema poisoning** | The document references a remote DTD or XSD that the parser fetches and trusts. | High |
| **Server-Side Request Forgery (SSRF)** | The parser dereferences a `SYSTEM` URI pointing at internal AWS / GCP metadata services. | Critical |
| **Stored XSS in PDF preview** | If the parsed XML content is later rendered in a browser surface (a preview, a copy of the data, an admin tray), unescaped attacker-controlled text becomes script. | Medium |
| **CFDI-format ambiguity** | SAT CFDI XML can be 3.3 or 4.0 with very different schemas. Accepting both ambiguously means classifier errors silently mis-categorize submissions. | Medium |
| **Document classifier dilution** | The current prevalidation classifier is rule-based + PDF-text aware. Adding XML pushes a new modality that the classifier has not been trained against. | Medium |

These risks are not theoretical. XXE and billion-laughs were both in OWASP Top 10 historically and remain on every responsible security checklist.

---

## 4. Why the request keeps coming up

Mexican tax submissions (CFDI 4.0, complementos) are XML-native. Some providers ask whether they can upload the XML directly instead of a PDF render. The product-side temptation is real:

- A real XML CFDI preserves SAT signatures and timestamps that the PDF render strips.
- Some downstream auditors prefer XML for machine-readability.

These are legitimate motivations. They are **not** sufficient justification to enable XML uploads platform-wide.

---

## 5. Conditions that would have to hold before reopening

If a future requirement justifies XML acceptance, the change is **not** "add `.xml` to `ALLOWED_FILE_EXTENSIONS`." The bare minimum hardening:

1. **Scope by requirement code.** Only specific requirement codes (e.g. a hypothetical `RX-CFDI-XML-001`) accept XML. The default for every other requirement stays PDF-only.
2. **Use a hardened parser.** Python: `defusedxml.ElementTree` or `defusedxml.lxml`. **Never** `xml.etree.ElementTree` from stdlib for untrusted input.
3. **Disable entity expansion.** No `resolve_entities`, no DTD loading, no external entity references. Reject any document that declares a DTD or external entity.
4. **Enforce a schema.** Validate against a pinned, repo-stored XSD per requirement code. Reject documents that fail validation.
5. **Quarantine before processing.** Write the file to a separate `quarantine/` storage prefix; run the parser inside a worker with no network access and minimal filesystem access; only promote to the canonical storage after validation succeeds.
6. **Size limit lower than PDF.** XML attacks need much smaller payloads than PDFs to do damage. Cap at 2 MB per file.
7. **Audit trail.** Every XML acceptance and rejection logged with `audit_events` rows.
8. **Threat-model review.** A security review documents the specific XML shapes accepted, the parser config, and the residual risk.
9. **Manual UI confirmation.** The upload card for the affected requirement code shows an explicit "XML aceptado" pill so users are not confused about which requirements accept what.

If any of these nine conditions cannot hold, **do not enable XML.**

---

## 6. How a future PR should propose XML acceptance

A PR that proposes enabling XML for a specific requirement must:

- Reference this document.
- Identify the exact requirement code (or codes).
- Show that the parser is `defusedxml`-based with entity expansion disabled.
- Ship a pinned XSD in the repo and reference it from a per-requirement validator.
- Add backend tests for: malformed XML, XXE attempt, billion-laughs, oversized payload, valid-schema happy path.
- Update the per-requirement `format` copy on the catalog so the provider knows XML is accepted for *that* requirement only.
- Get a second-reviewer sign-off explicitly on the security aspect.

A PR that proposes a blanket `.xml` allow-list change without the above must be rejected.

---

## 7. Quick reference for QA

| Question | Answer |
|---|---|
| Are XML uploads accepted today? | No. |
| Where is the rejection enforced? | `config.py` (default), `submission_service.py` (`assert_pdf_upload`), `prevalidation.py` (`allowed_file_type` rule). |
| Can a user enable XML by setting an env var? | Yes — `CHECKWISE_ALLOWED_FILE_EXTENSIONS=.pdf,.xml` would loosen the config. But the prevalidation rule would still flag the doc, and no specific XML parser is plumbed in. So XML uploads would store but produce error/warning signals and not auto-approve. **Do not do this in production.** |
| Should I open a follow-up issue if a customer asks for XML? | Yes. Link to this doc. Request the specific requirement code(s) and the auditor / regulator who requires XML over PDF. |

---

## 8. Reviewers / approvals

- **Product:** Jose Pablo — confirmed the "block by default" stance during the Stage 2.5 planning pass (2026-05-20).
- **Security:** required before any change that loosens this stance.
- **Legal:** required when the scope touches CFDI / SAT-signed XML to confirm the legal status of acceptance/storage.

---

*End of XML upload security recommendation.*
