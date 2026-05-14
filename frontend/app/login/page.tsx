"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Buildings,
  Key,
  ShieldCheck,
  Truck,
  UserCircle,
  Wrench,
  type Icon,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { ProviderAccessForm } from "@/components/checkwise/portal/provider-access-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { readPortalSession } from "@/lib/session/portal";

/**
 * Login / access entry.
 *
 * Three-role selector: Proveedor / Cliente / Administrador.
 *  - Proveedor + Cliente share the same access form for now (the
 *    backend does not yet expose a client_admin login path; the
 *    workspace token grants both views).
 *  - Administrador routes to a "configurado en fase posterior"
 *    placeholder. The legacy /admin/login route stays available for
 *    internal reviewers via a discreet link.
 *
 * TODO[backend-integration]: split the Proveedor/Cliente flows once
 * the API exposes a client_admin role with portfolio-wide read access.
 */

type RoleKey = "provider" | "client" | "admin";

interface RoleConfig {
  key: RoleKey;
  label: string;
  blurb: string;
  icon: Icon;
}

const ROLES: RoleConfig[] = [
  {
    key: "provider",
    label: "Proveedor",
    blurb: "Sube tu expediente y mantén tu cumplimiento al día.",
    icon: Truck,
  },
  {
    key: "client",
    label: "Cliente",
    blurb: "Audita el cumplimiento REPSE de tus proveedores.",
    icon: Buildings,
  },
  {
    key: "admin",
    label: "Administrador",
    blurb: "Operación interna de CheckWise / Legal Shelf.",
    icon: Wrench,
  },
];

export default function LoginPage() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [role, setRole] = useState<RoleKey>("provider");

  useEffect(() => {
    const existing = readPortalSession();
    if (existing) {
      // CheckWise 1.6: returning sessions enter the workspace
      // confirmation step first.
      router.replace("/portal/entra-a-tu-espacio");
      return;
    }
    setChecked(true);
  }, [router]);

  if (!checked) return <LoginSkeleton />;

  return (
    <main className="relative min-h-[100dvh] overflow-hidden">
      <BackgroundOrnaments />

      <div className="relative mx-auto flex min-h-[100dvh] max-w-3xl flex-col gap-8 px-5 py-10 lg:py-14">
        <header className="flex items-center justify-between cw-fade-up">
          <Link href="/" aria-label="Volver al inicio">
            <BrandLogo size="md" poweredBy />
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--text-link)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Volver al inicio
          </Link>
        </header>

        <section className="cw-fade-up space-y-6" style={{ animationDelay: "60ms" }}>
          <div className="space-y-2">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]">
              Iniciar sesión
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-[color:var(--text-primary)]">
              Bienvenido a CheckWise
            </h1>
            <p className="text-[15px] text-[color:var(--text-secondary)]">
              Selecciona tu tipo de cuenta para continuar.
            </p>
          </div>

          <RolePicker selected={role} onChange={setRole} />

          <div className="rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-md sm:p-8">
            {role === "admin" ? (
              <AdminPlaceholder />
            ) : (
              <RoleScopedForm role={role} />
            )}
          </div>

          <p className="text-center text-xs text-[color:var(--text-tertiary)]">
            ¿No tienes acceso aún?{" "}
            <a
              href="mailto:soporte@legalshelf.mx"
              className="text-[color:var(--text-link)] hover:underline"
            >
              Pídelo a tu cliente o contacta soporte.
            </a>
          </p>
        </section>
      </div>
    </main>
  );
}

// ─── Role picker ─────────────────────────────────────────────────

function RolePicker({
  selected,
  onChange,
}: {
  selected: RoleKey;
  onChange: (role: RoleKey) => void;
}) {
  return (
    <div role="radiogroup" aria-label="Tipo de cuenta" className="grid gap-3 sm:grid-cols-3">
      {ROLES.map((role) => {
        const isSelected = role.key === selected;
        const IconComponent = role.icon;
        return (
          <button
            key={role.key}
            type="button"
            role="radio"
            aria-checked={isSelected}
            onClick={() => onChange(role.key)}
            className={cn(
              "group cw-hover-lift flex flex-col items-start gap-2 rounded-lg border px-4 py-4 text-left transition-shadow",
              isSelected
                ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand-muted)] shadow-sm"
                : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] hover:border-[color:var(--border-strong)]",
            )}
          >
            <span
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-full",
                isSelected
                  ? "bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                  : "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]",
              )}
              aria-hidden="true"
            >
              <IconComponent className="h-5 w-5" weight="duotone" />
            </span>
            <div>
              <p
                className={cn(
                  "text-[14px] font-semibold leading-5",
                  isSelected
                    ? "text-[color:var(--text-brand)]"
                    : "text-[color:var(--text-primary)]",
                )}
              >
                {role.label}
              </p>
              <p className="mt-0.5 text-xs leading-4 text-[color:var(--text-secondary)]">
                {role.blurb}
              </p>
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ─── Role-scoped form ────────────────────────────────────────────

function RoleScopedForm({ role }: { role: "provider" | "client" }) {
  const isProvider = role === "provider";
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]">
          <ShieldCheck
            className="h-5 w-5 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
        </span>
        <div>
          <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
            {isProvider
              ? "Acceso de proveedor"
              : "Acceso de cliente"}
          </h2>
          <p className="text-xs text-[color:var(--text-secondary)]">
            {isProvider
              ? "Captura tu cliente, filial y RFC para abrir tu portal proveedor."
              : "Captura tu empresa para abrir tu vista cliente. La vista completa de portafolio se habilita en una fase próxima."}
          </p>
        </div>
      </div>

      {!isProvider && (
        <Alert variant="info">
          <AlertTitle>Vista cliente en fase preliminar</AlertTitle>
          <AlertDescription>
            Hoy compartimos el mismo formulario de acceso. La vista
            multi-proveedor del cliente se está construyendo —
            mientras tanto puedes recorrer el portal como referencia.
          </AlertDescription>
        </Alert>
      )}

      <ProviderAccessForm />

      <p className="border-t border-[color:var(--border-subtle)] pt-4 text-center text-xs text-[color:var(--text-tertiary)]">
        <Link
          href="/activate?token=demo"
          className="inline-flex items-center justify-center gap-1.5 text-[color:var(--text-link)] hover:underline"
        >
          <Key className="h-3 w-3" weight="bold" aria-hidden="true" />
          ¿Llegaste por correo de invitación? Activa tu cuenta aquí.
        </Link>
      </p>
    </div>
  );
}

// ─── Admin placeholder ───────────────────────────────────────────

function AdminPlaceholder() {
  return (
    <div className="flex flex-col items-start gap-5">
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]">
          <UserCircle
            className="h-5 w-5 text-[color:var(--text-teal)]"
            weight="duotone"
            aria-hidden="true"
          />
        </span>
        <div>
          <h2 className="text-base font-semibold text-[color:var(--text-primary)]">
            Portal administrativo
          </h2>
          <p className="text-xs text-[color:var(--text-secondary)]">
            Acceso interno de CheckWise / Legal Shelf.
          </p>
        </div>
      </div>

      <Alert variant="info">
        <AlertTitle>El portal administrativo se configurará en una fase posterior</AlertTitle>
        <AlertDescription>
          La vista de administrador completa — gestión de clientes,
          proveedores, invitaciones, plantillas REPSE y reportes
          ejecutivos — entra en V1.6. Mientras tanto, los revisores de
          Legal Shelf pueden usar el portal de revisión.
        </AlertDescription>
      </Alert>

      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline">
          <Link href="/admin/login">
            <span>Soy revisor interno</span>
            <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
          </Link>
        </Button>
        <Button asChild variant="ghost">
          <Link href="/">Volver al inicio</Link>
        </Button>
      </div>
    </div>
  );
}

// ─── Decorations + skeleton ──────────────────────────────────────

function BackgroundOrnaments() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="absolute -top-32 -left-24 h-[480px] w-[480px] rounded-full opacity-[0.18] blur-3xl"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--brand-navy)/0.55) 0%, transparent 70%)",
        }}
      />
      <div
        className="absolute -bottom-40 -right-24 h-[520px] w-[520px] rounded-full opacity-[0.14] blur-3xl"
        style={{
          background:
            "radial-gradient(circle, hsl(var(--brand-teal)/0.6) 0%, transparent 70%)",
        }}
      />
    </div>
  );
}

function LoginSkeleton() {
  return (
    <main className="mx-auto max-w-3xl px-5 py-16">
      <Skeleton className="h-8 w-32" />
      <div className="mt-10 grid gap-3 sm:grid-cols-3">
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
      </div>
      <Skeleton className="mt-6 h-[420px] w-full rounded-xl" />
    </main>
  );
}
