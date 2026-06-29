"use client";

import { useEffect } from "react";

/**
 * Error boundary of last resort. Next renders this IN PLACE of the root
 * layout when the layout itself (or anything above the per-section
 * boundaries) throws, so it MUST provide its own <html>/<body> and cannot
 * assume the app's providers, fonts, or CSS have loaded. Kept
 * dependency-free and inline-styled for that reason. Replaces Next's
 * default English crash page (audit public-auth "No root error boundary").
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global error boundary:", error);
  }, [error]);

  return (
    <html lang="es">
      <body
        style={{
          margin: 0,
          fontFamily:
            "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
          background: "#0b1220",
          color: "#e6edf6",
        }}
      >
        <main
          style={{
            minHeight: "100dvh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            padding: "24px",
            gap: "16px",
          }}
        >
          <p
            style={{
              fontSize: "12px",
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: "#8aa0b8",
              margin: 0,
            }}
          >
            CheckWise
          </p>
          <h1 style={{ fontSize: "24px", fontWeight: 700, margin: 0 }}>
            Algo salió mal
          </h1>
          <p
            style={{
              maxWidth: "30rem",
              color: "#b6c3d4",
              margin: 0,
              lineHeight: 1.5,
            }}
          >
            Ocurrió un error inesperado al cargar la página. Vuelve a
            intentarlo; si el problema continúa, escríbenos.
          </p>
          <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
            <button
              type="button"
              onClick={() => reset()}
              style={{
                padding: "10px 18px",
                borderRadius: "10px",
                border: "none",
                background: "#3ddc97",
                color: "#06231a",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Reintentar
            </button>
            {/* A crashed-root boundary must do a FULL-PAGE reload to recover —
                next/link client-side nav can't be trusted once the app shell
                has thrown. The plain anchor is intentional here. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/"
              style={{
                padding: "10px 18px",
                borderRadius: "10px",
                border: "1px solid #2b3b52",
                color: "#e6edf6",
                textDecoration: "none",
                fontWeight: 600,
              }}
            >
              Volver al inicio
            </a>
          </div>
          {error?.digest ? (
            <p style={{ fontSize: "11px", color: "#5f708c" }}>
              Ref: {error.digest}
            </p>
          ) : null}
        </main>
      </body>
    </html>
  );
}
