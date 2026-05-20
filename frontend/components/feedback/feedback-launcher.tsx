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
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import {
  Bug,
  Camera,
  ChatCenteredDots,
  Image as ImageIcon,
  Lightbulb,
  PaperPlaneRight,
  Trash,
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

  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const capturePage = useCallback(async () => {
    setCapturing(true);
    setOpen(false);
    // Wait one frame so the dialog actually leaves the DOM before we snap.
    await new Promise((r) => setTimeout(r, 80));
    try {
      const mod = await import("html2canvas");
      const html2canvas = mod.default;
      const canvas = await html2canvas(document.documentElement, {
        backgroundColor: null,
        useCORS: true,
        logging: false,
        ignoreElements: (el) =>
          el instanceof HTMLElement && el.dataset.feedbackLauncher === "true",
      });
      const blob: Blob | null = await new Promise((resolve) =>
        canvas.toBlob((b) => resolve(b), "image/png"),
      );
      if (!blob) {
        toast.error("No se pudo generar la captura.");
        return;
      }
      await attachBlob(blob);
    } catch (err) {
      console.error("feedback: html2canvas failed", err);
      toast.error("No se pudo capturar la página. Adjunta una imagen.");
    } finally {
      setCapturing(false);
      setOpen(true);
    }
  }, [attachBlob]);

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

      const commonPayload = {
        kind,
        description: trimmed,
        url: typeof window !== "undefined" ? window.location.href : "",
        path: typeof window !== "undefined" ? window.location.pathname : "",
        viewport:
          typeof window !== "undefined"
            ? `${window.innerWidth}x${window.innerHeight}`
            : "",
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
      <button
        type="button"
        aria-label="Reportar bug o sugerir mejora"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
        className={cn(
          "fixed bottom-4 right-4 z-50",
          "inline-flex items-center gap-2 rounded-full",
          "border border-[color:var(--border-strong)]",
          "bg-[color:var(--surface-overlay)] px-3.5 py-2",
          "text-[12px] font-medium text-[color:var(--text-primary)]",
          "shadow-md transition-[transform,box-shadow,background-color] duration-fast",
          "hover:bg-[color:var(--surface-hover)] hover:shadow-lg",
          "active:scale-[0.97]",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--border-focus)]/40 focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--surface-page)]",
        )}
      >
        <ChatCenteredDots className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
        <span className="hidden sm:inline">Reportar</span>
      </button>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (capturing) return;
          setOpen(next);
          if (!next) setError(null);
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
                <span
                  className={cn(
                    charCount > MAX_DESCRIPTION
                      ? "text-[color:var(--status-error-text)]"
                      : undefined,
                  )}
                >
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
              capturing={capturing}
              onPickFile={() => fileInputRef.current?.click()}
              onCapturePage={capturePage}
              onRemove={() => setScreenshot(null)}
            />

            <input
              ref={fileInputRef}
              type="file"
              accept="image/png"
              className="sr-only"
              onChange={onFilePicked}
            />

            <ContextStrip anonymous={isAnonymous} />

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

function ScreenshotPanel({
  screenshot,
  screenshotUrl,
  capturing,
  onPickFile,
  onCapturePage,
  onRemove,
}: {
  screenshot: Blob | null;
  screenshotUrl: string | null;
  capturing: boolean;
  onPickFile: () => void;
  onCapturePage: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onCapturePage}
          loading={capturing}
        >
          <Camera className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          Capturar página
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onPickFile}>
          <ImageIcon className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
          Subir PNG
        </Button>
        <span className="text-[11px] text-[color:var(--text-tertiary)]">
          o pega con Cmd+V
        </span>
      </div>
      {screenshot && screenshotUrl ? (
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
              PNG · {Math.round(screenshot.size / 1024)} KB
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
      ) : null}
    </div>
  );
}

function ContextStrip({ anonymous }: { anonymous: boolean }) {
  const [path, setPath] = useState("");
  const [viewport, setViewport] = useState("");
  useEffect(() => {
    if (typeof window === "undefined") return;
    setPath(window.location.pathname);
    setViewport(`${window.innerWidth}×${window.innerHeight}`);
  }, []);
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
