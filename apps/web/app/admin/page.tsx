"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CheckCircle,
  ClipboardText,
  SignOut,
  ShieldCheck,
  Users,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  type AdminSession,
  clearAdminSession,
  readAdminSession,
} from "@/lib/session/admin";

const REVIEWER_ROLES = ["reviewer", "internal_admin"] as const;

export default function AdminHomePage() {
  const router = useRouter();
  const [session, setSession] = useState<AdminSession | null>(null);

  useEffect(() => {
    const current = readAdminSession();
    if (!current) {
      router.replace("/login");
      return;
    }
    setSession(current);
  }, [router]);

  function onLogout() {
    clearAdminSession();
    router.replace("/login");
  }

  if (!session) return null;

  const canReview = session.roles.some((r) =>
    (REVIEWER_ROLES as readonly string[]).includes(r),
  );

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-5 py-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-3">
            <BrandLogo size="md" />
            <span className="hidden h-5 w-px bg-border sm:block" />
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Espacio interno
            </p>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Hola, {firstName(session.user.full_name)}
          </h1>
          <p className="text-sm text-muted-foreground">
            Sesión iniciada como{" "}
            <span className="font-medium text-foreground">{session.user.email}</span>.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {session.roles.map((role) => (
            <Badge key={role} variant="outline">
              {role.replace(/_/g, " ")}
            </Badge>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onLogout}
            className="active:scale-[0.98]"
          >
            <SignOut className="h-4 w-4" aria-hidden />
            Cerrar sesión
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Superficies disponibles</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Las herramientas que ya tienes acceso de acuerdo a tu rol.
          </p>
        </CardHeader>
        <CardContent>
          <ul className="grid gap-3 sm:grid-cols-2">
            {canReview ? (
              <li>
                <Link
                  href="/admin/reviewer"
                  className="block rounded-md border border-primary/30 bg-primary/5 p-4 transition-colors hover:bg-primary/10 active:scale-[0.99]"
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                      <ClipboardText className="h-4 w-4" aria-hidden />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="flex items-center justify-between gap-2 text-sm font-semibold">
                        Bandeja de revisión
                        <ArrowRight className="h-4 w-4 text-primary" aria-hidden />
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Cola de documentos esperando una decisión humana —
                        aprobar, rechazar, pedir aclaración o marcar excepción
                        legal.
                      </p>
                    </div>
                  </div>
                </Link>
              </li>
            ) : (
              <li className="rounded-md border border-border bg-white p-4 opacity-70">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                    <ClipboardText className="h-4 w-4" aria-hidden />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">Bandeja de revisión</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Requiere rol <code>reviewer</code> o{" "}
                      <code>internal_admin</code>.
                    </p>
                  </div>
                </div>
              </li>
            )}
            <li className="rounded-md border border-border bg-white p-4 opacity-70">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Users className="h-4 w-4" aria-hidden />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold">Vista de cliente</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Patch 8 — riesgo por proveedor para cada cliente bajo
                    administración.
                  </p>
                </div>
              </div>
            </li>
          </ul>
        </CardContent>
      </Card>

      {session.roles.includes("internal_admin") ? (
        <Card>
          <CardHeader>
            <CardTitle>Operaciones admin</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">
              Control plane interno. Cada cambio queda en el audit log.
            </p>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-3 sm:grid-cols-2">
              {[
                { href: "/admin/dashboard", label: "Resumen", desc: "Conteos operativos." },
                { href: "/admin/clients", label: "Clientes", desc: "Alta, edición y status." },
                { href: "/admin/vendors", label: "Proveedores", desc: "Alta, edición y status." },
                { href: "/admin/requirements", label: "Requisitos", desc: "Catálogo regulatorio." },
                { href: "/admin/calendar", label: "Calendario", desc: "Periodos y obligaciones." },
                { href: "/admin/metadata", label: "Metadata", desc: "Preview y descarga de XLSX automáticos." },
                { href: "/admin/audit-log", label: "Audit log", desc: "Explorador de eventos." },
                {
                  href: "/client/dashboard",
                  label: "Portal del cliente (preview)",
                  desc: "Vista cliente: semáforo + proveedores + actividad.",
                },
              ].map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="block rounded-md border border-primary/30 bg-primary/5 p-4 transition-colors hover:bg-primary/10"
                  >
                    <p className="flex items-center justify-between gap-2 text-sm font-semibold">
                      {item.label}
                      <ArrowRight className="h-4 w-4 text-primary" aria-hidden />
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{item.desc}</p>
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Estado de la sesión</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <Field
            icon={<CheckCircle className="h-4 w-4 text-emerald-600" aria-hidden />}
            label="Cuenta"
            value={`${session.user.full_name} · ${session.user.status}`}
          />
          <Field
            icon={<ShieldCheck className="h-4 w-4 text-primary" aria-hidden />}
            label="Roles"
            value={session.roles.length ? session.roles.join(", ") : "—"}
          />
          <Field
            icon={<Users className="h-4 w-4 text-primary" aria-hidden />}
            label="Organizaciones"
            value={`${session.organization_ids.length}`}
          />
          <Field
            icon={<CheckCircle className="h-4 w-4 text-emerald-600" aria-hidden />}
            label="Sesión vigente hasta"
            value={formatExpires(session.expires_at)}
          />
        </CardContent>
      </Card>
    </main>
  );
}

function Field({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border border-border bg-white p-3">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      <p className="mt-1 break-words text-sm font-medium">{value}</p>
    </div>
  );
}

function firstName(fullName: string): string {
  return fullName.split(" ")[0] ?? fullName;
}

function formatExpires(iso: string): string {
  try {
    return new Date(iso).toLocaleString("es-MX", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
