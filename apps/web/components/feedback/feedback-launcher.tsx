"use client";

/**
 * FeedbackLauncher — floating "Report bug / Suggest improvement" button.
 *
 * Mounted in two contexts:
 *
 *   1. Inside the post-login shells (AdminShell, ClientShell,
 *      PortalAppShell). Default mode. Hides itself when there is no
 *      admin JWT — logged-out and portal-only users never see it.
 *
 *   2. On the public landing page (`/`) via `allowPublic`. Renders
 *      regardless of session and submits to the unauthenticated
 *      `/api/v1/feedback/public` endpoint. Adds an optional
 *      reply-back email field since there's no signed-in identity.
 *
 * Reports go to ``POST /api/v1/feedback{,/public}`` which posts a
 * Block Kit message to the configured Slack channel, optionally with
 * a PNG screenshot attached as a thread reply.
 *
 * Screenshot inputs:
 *   - File picker (PNG only)
 *   - Clipboard paste — Cmd+V inside the dialog after taking an OS
 *     screenshot to clipboard.
 *   - "Capture this page" — html2canvas snapshot of the current
 *     viewport. The dialog is closed during capture so the launcher
 *     UI doesn't bleed into the screenshot.
 *
 * Also attaches the last ~20 console errors/warns via
 * ``snapshotConsoleLog()``, captured by ``startConsoleCapture()``
 * which is installed idempotently on mount.
 *
 * Capture sequence (bugfix, 2026-05-21)
 * -------------------------------------
 * Clicking the floating "Reportar" button now snaps the current page
 * BEFORE the dialog opens (``openWithCapture``), and the original
 * pathname / URL / viewport are locked into ``originalContextRef`` at
 * the same moment. Submission reads from that ref rather than live
 * ``window.location.*`` so the screenshot, the Slack route label, and
 * the recorded URL all describe the page the user was on at the
 * instant they clicked — never the dialog itself, never a route the
 * user navigated to afterwards. The in-dialog "Capturar página"
 * button stays as an explicit re-capture (e.g. for users who want to
 * scroll first) but now waits long enough for the Radix exit
 * animation, and html2canvas excludes any ``[data-screenshot-exclude]``
 * node so a portal-rendered dialog overlay can't bleed in.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import {
  Bug,
  ChatCenteredDots,
  Image as ImageIcon,
  Lightbulb,
  PaperPlaneRight,
  Trash,
  X,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { readAdminSession } from "@/lib/session/admin";
import {
  submitFeedback,
  submitPublicFeedback,
  type FeedbackKind,
} from "@/lib/api/feedback";
import {
  snapshotConsoleLog,
  startConsoleCapture,
} from "@/lib/feedback/console-capture";

const MIN_DESCRIPTION = 10;
const MAX_DESCRIPTION = 4000;
const MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024;
const MAX_CONTACT_EMAIL = 256;
const PNG_MAGIC = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

export interface FeedbackLauncherProps {
  /**
   * When ``true``, the launcher renders even without a signed-in
   * session and submits via the unauthenticated public endpoint.
   * Used on the marketing landing page.
   *
   * When the user IS signed in, the launcher still prefers the
   * authenticated endpoint so the Slack message includes their
   * identity and roles.
   *
   * Default: ``false`` — preserves the original behavior of hiding
   * for logged-out visitors.
   */
  allowPublic?: boolean;
}

export function FeedbackLauncher({
  allowPublic = false,
}: FeedbackLauncherProps = {}) {
  const pathname = usePathname();
  const [hasSession, setHasSession] = useState(false);
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<FeedbackKind>("bug");
  const [description, setDescription] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [screenshot, setScreenshot] = useState<Blob | null>(null);
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // §5.1 — the floating launcher is dismissible. A provider who finds the
  // fixed bottom-right FAB invasive can hide it for the session; the
  // always-available "Reportar problema" entry in the sidebar (which fires
  // the same ``checkwise:open-feedback`` event the Dialog listens for)
  // remains, so dismissing never strands the feedback path. Read in an
  // effect (not during render) to avoid an SSR/client hydration mismatch.
  const [dismissed, setDismissed] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      if (window.sessionStorage.getItem("checkwise.feedback.fab.dismissed") === "1") {
        setDismissed(true);
      }
    } catch {
      // sessionStorage can throw in private-mode / sandboxed frames — the
      // FAB just stays visible, which is the safe default.
    }
  }, []);
  const dismissFab = useCallback(() => {
    setDismissed(true);
    try {
      window.sessionStorage.setItem("checkwise.feedback.fab.dismissed", "1");
    } catch {
      // Best-effort persistence; the in-memory state still hides it now.
    }
  }, []);

  const fileInputRef = useRef<HTMLInputElement>(null);
  // Bugfix (2026-05-21) — original page context captured at the
  // moment the floating button is clicked. ``null`` until the user
  // clicks; reset when the dialog closes. Submit prefers this over
  // live window.location so a navigation between click and submit
  // (or the dialog itself) can't desync the screenshot from the
  // reported route.
  const originalContextRef = useRef<{
    url: string;
    path: string;
    viewport: string;
    capturedAt: string;
  } | null>(null);

  // Install the console capture once and re-check session whenever the
  // route changes (covers logout-then-login in the same tab).
  useEffect(() => {
    startConsoleCapture();
  }, []);
  useEffect(() => {
    setHasSession(Boolean(readAdminSession()));
  }, [pathname]);

  // Revoke the screenshot preview URL on change/unmount to avoid leaks.
  useEffect(() => {
    if (!screenshot) {
      setScreenshotUrl(null);
      return;
    }
    const url = URL.createObjectURL(screenshot);
    setScreenshotUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [screenshot]);

  const resetForm = useCallback(() => {
    setKind("bug");
    setDescription("");
    setContactEmail("");
    setScreenshot(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const attachBlob = useCallback(async (blob: Blob) => {
    if (blob.size > MAX_SCREENSHOT_BYTES) {
      toast.error("La captura supera 5 MB.");
      return;
    }
    const head = new Uint8Array(await blob.slice(0, 8).arrayBuffer());
    const isPng = PNG_MAGIC.every((b, i) => head[i] === b);
    if (!isPng) {
      toast.error("La captura debe ser PNG.");
      return;
    }
    setScreenshot(blob);
  }, []);

  const onFilePicked = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) return;
      await attachBlob(file);
    },
    [attachBlob],
  );

  const onPaste = useCallback(
    async (event: React.ClipboardEvent<HTMLDivElement>) => {
      const items = event.clipboardData?.items;
      if (!items) return;
      let sawNonPngImage = false;
      for (const item of items) {
        if (item.kind !== "file") continue;
        if (item.type === "image/png") {
          event.preventDefault();
          const blob = item.getAsFile();
          if (blob) await attachBlob(blob);
          return;
        }
        if (item.type.startsWith("image/")) {
          sawNonPngImage = true;
        }
      }
      if (sawNonPngImage) {
        // Block the paste (the image isn't going to the textarea anyway)
        // and tell the user why nothing happened.
        event.preventDefault();
        toast.error("Solo se aceptan capturas en PNG.");
      }
    },
    [attachBlob],
  );

  // ``html2canvas`` ignore predicate. Excludes the floating launcher
  // wrapper AND anything carrying ``data-screenshot-exclude`` (any
  // open Radix Dialog overlay/content carries it via the local
  // ui/dialog wrapper). Belt-and-suspenders: even if a portal hasn't
  // fully unmounted during the recapture flow, html2canvas walks past
  // it.
  const shouldIgnoreForScreenshot = useCallback((el: Element): boolean => {
    if (!(el instanceof HTMLElement)) return false;
    if (el.dataset.feedbackLauncher === "true") return true;
    if (el.dataset.screenshotExclude === "true") return true;
    return false;
  }, []);

  /**
   * Bugfix (2026-05-21) — primary capture path.
   *
   * Runs synchronously when the floating "Reportar" button is
   * clicked, BEFORE the dialog opens. Locks the original route
   * metadata into ``originalContextRef`` and produces a screenshot of
   * the page the user was actually looking at. The dialog opens only
   * after the snap is in hand (or fails gracefully).
   */
  const openWithCapture = useCallback(async () => {
    if (capturing || open) return;
    // 1. Snapshot route metadata FIRST so even an html2canvas crash
    //    can't drop the original context.
    if (typeof window !== "undefined") {
      originalContextRef.current = {
        url: window.location.href,
        path: window.location.pathname,
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        capturedAt: new Date().toISOString(),
      };
    }
    // 2. Run html2canvas on the current page. The dialog is not yet
    //    mounted so there's nothing to exclude beyond the launcher
    //    chip itself. Spinner on the chip tells the user something
    //    is happening (capture is typically 200-500ms).
    setCapturing(true);
    try {
      const mod = await import("html2canvas");
      const html2canvas = mod.default;
      const canvas = await html2canvas(document.documentElement, {
        backgroundColor: null,
        useCORS: true,
        logging: false,
        ignoreElements: shouldIgnoreForScreenshot,
      });
      const blob: Blob | null = await new Promise((resolve) =>
        canvas.toBlob((b) => resolve(b), "image/png"),
      );
      if (blob) {
        await attachBlob(blob);
      } else {
        // Capture succeeded but blob conversion failed — open the
        // dialog anyway so the user can describe the issue and
        // attach an image manually.
        toast.error("No se pudo generar la captura automática. Adjunta una imagen.");
      }
    } catch (err) {
      // Intentional console.error (not a leftover): the feedback
      // console-capture interceptor records it, so the capture failure
      // itself shows up in the submitted report's console log.
      console.error("feedback: auto-capture failed", err);
      toast.error("No pudimos capturar la página. Adjunta una imagen.");
    } finally {
      setCapturing(false);
      setOpen(true);
    }
  }, [attachBlob, capturing, open, shouldIgnoreForScreenshot]);

  // UX simplification (2026-05-21) — the in-dialog "Capturar página"
  // recapture path was removed. Auto-capture at button click now
  // covers the primary case; users who specifically want a different
  // screenshot can still paste with Cmd+V (the dialog's onPaste
  // handler stays wired) or use the manual upload fallback the
  // ScreenshotPanel surfaces only when auto-capture failed. Removing
  // the close-then-snap-then-reopen ping-pong also eliminates the
  // possibility of the dialog re-mounting with the locked
  // ``originalContextRef`` stale.

  // Allow other shell components (e.g. the portal sidebar's compact
  // "Reportar" entry) to open the launcher dialog via a window event
  // without having to hold a ref to this component. Custom event:
  // ``checkwise:open-feedback``. Mounted once globally so every
  // page-level dispatcher reaches the same instance.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = () => {
      void openWithCapture();
    };
    window.addEventListener("checkwise:open-feedback", handler);
    return () => {
      window.removeEventListener("checkwise:open-feedback", handler);
    };
  }, [openWithCapture]);

  const onSubmit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      const trimmed = description.trim();
      if (trimmed.length < MIN_DESCRIPTION) {
        setError(`Cuéntanos un poco más (mínimo ${MIN_DESCRIPTION} caracteres).`);
        return;
      }
      const session = readAdminSession();
      // No session + not allowed to fall back → tell the user. This
      // shouldn't normally happen because the !hasSession-and-not-public
      // path doesn't render the launcher at all, but a session can
      // expire while the dialog is open.
      if (!session && !allowPublic) {
        toast.error("Tu sesión expiró. Vuelve a iniciar sesión.");
        return;
      }

      // Bugfix (2026-05-21) — prefer ``originalContextRef.current``
      // (locked at the moment the floating button was clicked) over
      // live ``window.location.*``. Falls back to live values only
      // when the launcher was opened by a programmatic path that
      // didn't go through ``openWithCapture`` (which shouldn't happen
      // in practice; the fallback is defensive only). This keeps the
      // route the user sees in Slack identical to the route in the
      // attached screenshot.
      const liveUrl = typeof window !== "undefined" ? window.location.href : "";
      const livePath =
        typeof window !== "undefined" ? window.location.pathname : "";
      const liveViewport =
        typeof window !== "undefined"
          ? `${window.innerWidth}x${window.innerHeight}`
          : "";
      const originalContext = originalContextRef.current;
      const commonPayload = {
        kind,
        description: trimmed,
        url: originalContext?.url ?? liveUrl,
        path: originalContext?.path ?? livePath,
        viewport: originalContext?.viewport ?? liveViewport,
        userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "",
        consoleLogs: snapshotConsoleLog(),
        screenshot,
      };

      setSubmitting(true);
      setError(null);
      const result = session
        ? await submitFeedback(session.access_token, commonPayload)
        : await submitPublicFeedback({
            ...commonPayload,
            contactEmail: contactEmail.trim() || undefined,
          });
      setSubmitting(false);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      toast.success(
        result.delivered
          ? "¡Gracias! Tu reporte se envió al equipo CheckWise."
          : "Reporte recibido (entrega a Slack aún sin configurar).",
      );
      setOpen(false);
      // Clear the locked original-context — the next click starts a
      // fresh capture from wherever the user is then.
      originalContextRef.current = null;
      resetForm();
    },
    [description, kind, screenshot, contactEmail, allowPublic, resetForm],
  );

  const charCount = description.trim().length;
  const submitDisabled =
    submitting || capturing || charCount < MIN_DESCRIPTION;

  // Memoize the button label / accent so the floating chip reflects intent.
  const accent = useMemo(
    () => (kind === "bug" ? "Reportar bug" : "Sugerir mejora"),
    [kind],
  );

  // Render rules:
  //   - Authenticated shells (allowPublic=false): only when a JWT exists.
  //   - Landing page (allowPublic=true): always render; anonymous
  //     submissions go through the public endpoint.
  const isAnonymous = !hasSession;
  if (isAnonymous && !allowPublic) return null;

  return (
    <div data-feedback-launcher="true">
      {/* §5.1 — the FAB is hidden once the provider dismisses it (the
          sidebar "Reportar problema" entry keeps the path open). The
          ``feedback-launcher-fab`` wrapper still lets the Wise drawer hide
          this while it owns the right gutter (see globals.css). */}
      {!dismissed ? (
        <div className="feedback-launcher-fab fixed bottom-4 right-4 z-50">
          <button
            type="button"
            aria-label={
              capturing
                ? "Capturando la página actual…"
                : "Reportar bug o sugerir mejora"
            }
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-busy={capturing}
            disabled={capturing}
            onClick={openWithCapture}
            className={cn(
              "inline-flex items-center gap-2 rounded-full",
              "border border-[color:var(--border-strong)]",
              "bg-[color:var(--surface-overlay)] px-3.5 py-2",
              "text-[12px] font-medium text-[color:var(--text-primary)]",
              "shadow-md transition-[transform,box-shadow,background-color] duration-fast",
              "hover:bg-[color:var(--surface-hover)] hover:shadow-lg",
              "active:scale-[0.97]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--surface-page)]",
              "disabled:cursor-progress disabled:opacity-80",
            )}
          >
            <ChatCenteredDots
              className={cn(
                "h-3.5 w-3.5",
                capturing && "animate-pulse",
              )}
              weight="bold"
              aria-hidden="true"
            />
            <span className="hidden sm:inline">
              {capturing ? "Capturando…" : "Reportar"}
            </span>
          </button>
          <button
            type="button"
            aria-label="Ocultar el botón de reportar"
            title="Ocultar este botón (sigue disponible en el menú lateral)"
            onClick={dismissFab}
            className={cn(
              "absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center",
              "rounded-full border border-[color:var(--border-strong)]",
              "bg-[color:var(--surface-overlay)] text-[color:var(--text-secondary)] shadow-sm",
              "transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--text-primary)]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40",
            )}
          >
            <X className="h-3 w-3" weight="bold" aria-hidden="true" />
          </button>
        </div>
      ) : null}

      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (capturing) return;
          setOpen(next);
          if (!next) {
            setError(null);
            // Bugfix (2026-05-21) — clear the locked context when the
            // user dismisses without submitting. The next click starts
            // a fresh capture from wherever they are then.
            originalContextRef.current = null;
          }
        }}
      >
        <DialogContent
          className="max-w-xl"
          onPaste={onPaste}
        >
          <DialogHeader>
            <DialogTitle>Reportar a CheckWise</DialogTitle>
            <DialogDescription>
              {isAnonymous
                ? "Cuéntanos qué viste o qué se puede mejorar. Es anónimo — opcionalmente déjanos un email para responderte."
                : "Describe lo que viste o lo que se puede mejorar. Adjunta una captura si ayuda — pega con Cmd+V, súbela, o captura la página actual."}
            </DialogDescription>
          </DialogHeader>

          <form className="flex flex-col gap-4" onSubmit={onSubmit}>
            <KindToggle value={kind} onChange={setKind} />

            {isAnonymous ? (
              <Field
                label="Tu email (opcional)"
                htmlFor="feedback-contact-email"
                helper="Sólo si quieres que te respondamos."
              >
                <Input
                  id="feedback-contact-email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="tu@correo.com"
                  value={contactEmail}
                  onChange={(e) => setContactEmail(e.target.value)}
                  maxLength={MAX_CONTACT_EMAIL}
                />
              </Field>
            ) : null}

            <Field
              label="¿Qué pasó?"
              htmlFor="feedback-description"
              required
              trailing={
                <span>
                  {charCount}/{MAX_DESCRIPTION}
                </span>
              }
              error={error}
            >
              <Textarea
                id="feedback-description"
                placeholder={
                  kind === "bug"
                    ? "Ej. al subir un PDF de 12 MB el botón Guardar se queda gris…"
                    : "Ej. sería útil ver el RFC del proveedor desde la lista…"
                }
                value={description}
                onChange={(e) => {
                  setDescription(e.target.value);
                  if (error) setError(null);
                }}
                maxLength={MAX_DESCRIPTION}
                rows={5}
                autoFocus
              />
            </Field>

            <ScreenshotPanel
              screenshot={screenshot}
              screenshotUrl={screenshotUrl}
              onPickFile={() => fileInputRef.current?.click()}
              onRemove={() => setScreenshot(null)}
            />

            <input
              ref={fileInputRef}
              type="file"
              accept="image/png"
              className="sr-only"
              onChange={onFilePicked}
            />

            <ContextStrip
              anonymous={isAnonymous}
              originalContext={originalContextRef.current}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setOpen(false)}
                disabled={submitting}
              >
                Cancelar
              </Button>
              <Button type="submit" loading={submitting} disabled={submitDisabled}>
                <PaperPlaneRight className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
                {accent}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function KindToggle({
  value,
  onChange,
}: {
  value: FeedbackKind;
  onChange: (next: FeedbackKind) => void;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Tipo de reporte"
      className="grid grid-cols-2 gap-2"
    >
      <KindOption
        value="bug"
        active={value === "bug"}
        onChange={onChange}
        icon={<Bug className="h-4 w-4" weight="bold" aria-hidden="true" />}
        title="Bug"
        subtitle="Algo no funcionó"
      />
      <KindOption
        value="improvement"
        active={value === "improvement"}
        onChange={onChange}
        icon={<Lightbulb className="h-4 w-4" weight="bold" aria-hidden="true" />}
        title="Mejora"
        subtitle="Algo podría ser mejor"
      />
    </div>
  );
}

function KindOption({
  value,
  active,
  onChange,
  icon,
  title,
  subtitle,
}: {
  value: FeedbackKind;
  active: boolean;
  onChange: (next: FeedbackKind) => void;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={() => onChange(value)}
      className={cn(
        "flex items-start gap-2 rounded-md border px-3 py-2 text-left",
        "transition-colors duration-fast",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40",
        active
          ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand)]/10 text-[color:var(--text-primary)]"
          : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] text-[color:var(--text-secondary)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--surface-hover)]",
      )}
    >
      <span
        className={cn(
          "mt-0.5",
          active
            ? "text-[color:var(--text-brand)]"
            : "text-[color:var(--text-tertiary)]",
        )}
      >
        {icon}
      </span>
      <span className="flex flex-col">
        <span className="text-[13px] font-medium leading-tight">{title}</span>
        <span className="text-[11px] text-[color:var(--text-tertiary)]">
          {subtitle}
        </span>
      </span>
    </button>
  );
}

/**
 * UX simplification (2026-05-21) — dialog no longer surfaces capture
 * controls. The auto-capture at floating-button click is the primary
 * (and effectively only) path; this panel just confirms the
 * screenshot is there.
 *
 * Two states:
 *   - Screenshot attached → thumbnail + "Captura adjunta · PNG · X KB"
 *     + a small "Quitar" trash button (lets the user drop the
 *     auto-capture if they don't want any image at all).
 *   - Screenshot null (auto-capture failed silently with a toast) →
 *     show a single "Subir PNG manualmente" fallback so the user
 *     isn't stranded. No "Capturar página" button (the auto-capture
 *     already ran), no Cmd+V hint (paste handler stays wired on the
 *     dialog so power users can still paste — just no visible
 *     prompt).
 */
function ScreenshotPanel({
  screenshot,
  screenshotUrl,
  onPickFile,
  onRemove,
}: {
  screenshot: Blob | null;
  screenshotUrl: string | null;
  onPickFile: () => void;
  onRemove: () => void;
}) {
  if (screenshot && screenshotUrl) {
    return (
      <div className="flex items-start gap-3 rounded-md border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-2">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={screenshotUrl}
          alt="Captura adjunta"
          className="h-16 w-24 rounded-sm border border-[color:var(--border-subtle)] object-cover"
        />
        <div className="flex flex-1 flex-col text-[12px] text-[color:var(--text-secondary)]">
          <span className="font-medium text-[color:var(--text-primary)]">
            Captura adjunta
          </span>
          <span className="font-mono text-[11px] text-[color:var(--text-tertiary)]">
            PNG · {Math.round(screenshot.size / 1024)} KB · capturada
            automáticamente
          </span>
        </div>
        <button
          type="button"
          onClick={onRemove}
          aria-label="Quitar captura"
          className="rounded-sm p-1 text-[color:var(--text-tertiary)] transition-colors hover:bg-[color:var(--surface-hover)] hover:text-[color:var(--status-error-text)]"
        >
          <Trash className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        </button>
      </div>
    );
  }
  // Fallback: auto-capture failed (a toast already explained why).
  // Single discrete button so the user can attach manually instead
  // of being stranded without a screenshot.
  return (
    <div className="flex items-center gap-2 rounded-md border border-dashed border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)]/40 p-3 text-[12px] text-[color:var(--text-secondary)]">
      <ImageIcon
        className="h-3.5 w-3.5 shrink-0 text-[color:var(--text-tertiary)]"
        weight="bold"
        aria-hidden="true"
      />
      <span className="flex-1">
        No pudimos adjuntar la captura automática.
      </span>
      <Button type="button" size="sm" variant="outline" onClick={onPickFile}>
        Subir PNG
      </Button>
    </div>
  );
}

function ContextStrip({
  anonymous,
  originalContext,
}: {
  anonymous: boolean;
  // Bugfix (2026-05-21) — prefer the locked context so the disclosed
  // route matches what the screenshot shows and what the backend
  // receives. Falls back to live values if (defensively) no locked
  // context is present.
  originalContext: {
    url: string;
    path: string;
    viewport: string;
    capturedAt: string;
  } | null;
}) {
  const [livePath, setLivePath] = useState("");
  const [liveViewport, setLiveViewport] = useState("");
  useEffect(() => {
    if (typeof window === "undefined") return;
    setLivePath(window.location.pathname);
    setLiveViewport(`${window.innerWidth}×${window.innerHeight}`);
  }, []);
  const path = originalContext?.path || livePath;
  const viewport =
    originalContext?.viewport.replace("x", "×") || liveViewport;
  // Public visitors don't have a "usuario" to attach; show the same
  // strip with that token replaced by a hashed source fingerprint so
  // the consent disclosure stays honest.
  const identityToken = anonymous ? "huella IP (anónima)" : "usuario";
  return (
    <div className="rounded-md border border-dashed border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)]/40 px-3 py-2 font-mono text-[11px] text-[color:var(--text-tertiary)]">
      <span className="text-[color:var(--text-secondary)]">Se enviará:</span>{" "}
      ruta <span className="text-[color:var(--text-primary)]">{path || "—"}</span>{" "}
      · viewport <span className="text-[color:var(--text-primary)]">{viewport}</span>{" "}
      · navegador · {identityToken} · últimos errores de consola
    </div>
  );
}
