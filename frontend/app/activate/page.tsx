"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  Buildings,
  Check,
  CheckCircle,
  Eye,
  EyeSlash,
  Key,
  ShieldCheck,
  Truck,
  UserCircle,
  Warning,
  WarningCircle,
  type Icon,
} from "@phosphor-icons/react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Stepper, type StepperStep } from "@/components/ui/stepper";
import {
  evaluatePassword,
  inferFromEmail,
  type EmailInference,
} from "@/lib/email-inference";
import type { InvitationRole } from "@/lib/email/welcome";
import {
  MOCK_TEMP_CODE,
  setPassword,
  submitIdentity,
  verifyTempCredentials,
  type ActivationError,
  type ActivationSession,
} from "@/lib/mock/activation";
import {
  consumeInvitation,
  verifyToken,
  type Invitation,
} from "@/lib/mock/invitations";
import { cn } from "@/lib/utils";
import { writePortalSession } from "@/lib/session/portal";

const STEPS: StepperStep[] = [
  { id: "credentials", label: "Tus credenciales" },
  { id: "password", label: "Nueva contraseña" },
  { id: "identity", label: "Tus datos" },
];

type StepIndex = 0 | 1 | 2 | 3; // 3 = success

const ERROR_COPY: Record<ActivationError, { title: string; body: string }> = {
  invalid_credentials: {
    title: "Credenciales inválidas",
    body: "Revisa el correo y el código temporal. Si crees que las recibiste correctas, contacta a soporte.",
  },
  expired_invitation: {
    title: "Tu invitación expiró",
    body: "Pide a tu cliente que te genere una nueva invitación. Las invitaciones caducan a los 7 días.",
  },
  missing_invitation: {
    title: "Falta información",
    body: "Captura tu correo y el código temporal que recibiste.",
  },
  network: {
    title: "Sin conexión",
    body: "Revisa tu conexión a internet e intenta de nuevo.",
  },
};

export default function ActivatePage() {
  return (
    <Suspense fallback={<ActivateSkeleton />}>
      <ActivateClient />
    </Suspense>
  );
}

function ActivateClient() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token");

  const [tokenChecked, setTokenChecked] = useState(false);
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [tokenError, setTokenError] = useState<"unknown" | "expired" | null>(null);

  const [stepIndex, setStepIndex] = useState<StepIndex>(0);
  const [session, setSession] = useState<ActivationSession | null>(null);
  const [error, setError] = useState<ActivationError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // ── Token verification on mount ────────────────────────────────
  useEffect(() => {
    if (!token) {
      setTokenChecked(true);
      return;
    }
    const result = verifyToken(token);
    if (!result.ok || !result.invitation) {
      setTokenError(result.error ?? "unknown");
      setTokenChecked(true);
      return;
    }
    setInvitation(result.invitation);
    // Skip the manual credentials step — token-based entry pre-fills
    // the activation session with the invited email.
    setSession({
      activation_token: `tok-${result.invitation.token}`,
      email: result.invitation.email,
      company_hint: result.invitation.company_hint,
    });
    setStepIndex(1);
    setTokenChecked(true);
  }, [token]);

  const inference: EmailInference | null = useMemo(
    () => (session ? inferFromEmail(session.email) : null),
    [session],
  );

  const goBack = useCallback(() => {
    setError(null);
    // From the password step, only allow going back to credentials
    // when there's no token-based session pinning the email.
    setStepIndex((i) => {
      if (i === 1 && invitation) return i;
      return i > 0 ? ((i - 1) as StepIndex) : i;
    });
  }, [invitation]);

  if (!tokenChecked) return <ActivateSkeleton />;

  return (
    <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
      <div className="mx-auto flex min-h-[100dvh] max-w-3xl flex-col gap-8 px-5 py-10 lg:py-14">
        <header className="flex items-center justify-between">
          <Link href="/" aria-label="Volver al inicio">
            <BrandLogo size="md" />
          </Link>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[color:var(--text-link)] hover:underline"
          >
            <ArrowLeft className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            Volver al inicio
          </Link>
        </header>

        {invitation && stepIndex < 3 && <InvitationBanner invitation={invitation} />}

        {tokenError && (
          <Alert variant="error">
            <AlertTitle>
              {tokenError === "expired"
                ? "Tu invitación expiró"
                : "No reconocimos este enlace"}
            </AlertTitle>
            <AlertDescription>
              {tokenError === "expired"
                ? "Pide a quien te invitó que genere una nueva invitación."
                : "El enlace puede haberse roto o nunca llegó a emitirse. Puedes activar tu cuenta capturando tus credenciales temporales aquí mismo."}
            </AlertDescription>
          </Alert>
        )}

        {stepIndex < 3 && (
          <Stepper steps={STEPS} currentIndex={stepIndex as 0 | 1 | 2} />
        )}

        <section
          aria-live="polite"
          className="cw-fade-up rounded-xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-6 shadow-md sm:p-8"
        >
          {stepIndex === 0 && (
            <CredentialsStep
              error={error}
              submitting={submitting}
              onSubmit={async (creds) => {
                setError(null);
                setSubmitting(true);
                const result = await verifyTempCredentials(creds);
                setSubmitting(false);
                if (!result.ok) {
                  setError(result.error);
                  return;
                }
                setSession(result.data);
                setStepIndex(1);
              }}
            />
          )}

          {stepIndex === 1 && session && (
            <PasswordStep
              email={session.email}
              error={error}
              submitting={submitting}
              canGoBack={!invitation}
              onBack={goBack}
              onSubmit={async (password) => {
                setError(null);
                setSubmitting(true);
                const result = await setPassword(session.activation_token, password);
                setSubmitting(false);
                if (!result.ok) {
                  setError(result.error);
                  return;
                }
                setStepIndex(2);
              }}
            />
          )}

          {stepIndex === 2 && session && inference && (
            <IdentityStep
              email={session.email}
              inference={inference}
              presetCompany={invitation?.company_hint ?? null}
              presetRole={invitation?.role ?? "provider"}
              error={error}
              submitting={submitting}
              onBack={goBack}
              onSubmit={async (payload) => {
                setError(null);
                setSubmitting(true);
                const result = await submitIdentity(session.activation_token, {
                  first_name: payload.first_name,
                  last_name: payload.last_name,
                  email: payload.email,
                  company: payload.company,
                });
                setSubmitting(false);
                if (!result.ok) {
                  setError(result.error);
                  return;
                }
                // Mark the invitation consumed so the same token can't
                // be reused (matters when we go to real auth).
                if (invitation) consumeInvitation(invitation.token);

                writePortalSession({
                  workspace_id: result.data.workspace_id,
                  access_token: result.data.access_token,
                  persona_type: "moral",
                  client_name:
                    payload.role === "client" ? payload.company : "Cliente por confirmar",
                  vendor_name: payload.company,
                  vendor_rfc: "PENDIENTE",
                  filial_name: null,
                  contract_reference: null,
                  onboarding_completed_at: null,
                });
                setStepIndex(3);
                // CheckWise 1.6: confirm workspace before onboarding.
                setTimeout(() => router.push("/portal/entra-a-tu-espacio"), 1800);
              }}
            />
          )}

          {stepIndex === 3 && <SuccessStep />}
        </section>

        {!invitation && stepIndex === 0 && (
          <p className="text-center text-xs text-[color:var(--text-tertiary)]">
            Para esta demo, el código temporal es{" "}
            <span className="font-mono font-semibold text-[color:var(--text-brand)]">
              {MOCK_TEMP_CODE}
            </span>
            .
          </p>
        )}
      </div>
    </main>
  );
}

// ─── Invitation banner ──────────────────────────────────────────

function InvitationBanner({ invitation }: { invitation: Invitation }) {
  const RoleIcon: Icon = invitation.role === "client" ? Buildings : Truck;
  return (
    <div className="cw-fade-up flex items-center gap-3 rounded-lg border border-[color:var(--surface-teal-muted)] bg-[color:var(--surface-teal-muted)]/40 p-4">
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[color:var(--surface-raised)] text-[color:var(--text-teal)]"
        aria-hidden="true"
      >
        <RoleIcon className="h-5 w-5" weight="duotone" />
      </span>
      <div className="min-w-0">
        <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-teal)]">
          Invitación verificada · {invitation.role === "client" ? "Cliente" : "Proveedor"}
        </p>
        <p className="mt-0.5 text-[13px] leading-5 text-[color:var(--text-primary)]">
          <span className="font-medium">{invitation.inviter}</span>
          {" te invitó como "}
          <strong>{invitation.role === "client" ? "cliente" : "proveedor"}</strong>
          {invitation.company_hint && (
            <>
              {" de "}
              <strong>{invitation.company_hint}</strong>
            </>
          )}
          . Sigue los pasos para activar tu cuenta.
        </p>
      </div>
    </div>
  );
}

// ─── Loading skeleton ───────────────────────────────────────────

function ActivateSkeleton() {
  return (
    <main className="min-h-[100dvh] bg-[color:var(--surface-page)]">
      <div className="mx-auto flex min-h-[100dvh] max-w-3xl flex-col gap-6 px-5 py-10 lg:py-14">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-[480px] w-full rounded-xl" />
      </div>
    </main>
  );
}

// ─── Step 1 — temp credentials ──────────────────────────────────

interface CredentialsStepProps {
  error: ActivationError | null;
  submitting: boolean;
  onSubmit: (creds: { email: string; temp_code: string }) => Promise<void>;
}

function CredentialsStep({ error, submitting, onSubmit }: CredentialsStepProps) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void onSubmit({ email, temp_code: code });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]">
          <Key
            className="h-5 w-5 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-[color:var(--text-primary)]">
            Activa tu cuenta de CheckWise
          </h1>
          <p className="text-[13px] text-[color:var(--text-secondary)]">
            Usa el correo donde recibiste tu invitación y el código temporal.
          </p>
        </div>
      </div>

      {error && (
        <Alert variant="error">
          <AlertTitle>{ERROR_COPY[error].title}</AlertTitle>
          <AlertDescription>{ERROR_COPY[error].body}</AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4">
        <Field
          label="Correo electrónico"
          htmlFor="activation-email"
          required
          helper="Es el correo donde llegó tu invitación."
        >
          <Input
            id="activation-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="tu.correo@empresa.com"
            autoComplete="email"
            autoFocus
          />
        </Field>

        <Field
          label="Código temporal"
          htmlFor="activation-code"
          required
          helper="Tu invitación trae un código de 12 caracteres."
        >
          <Input
            id="activation-code"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="CW-XXXX-XXXX"
            autoComplete="one-time-code"
            className="font-mono uppercase tracking-wider"
          />
        </Field>
      </div>

      <Button type="submit" loading={submitting} size="lg" className="w-full">
        <span>Verificar mi invitación</span>
        {!submitting && <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />}
      </Button>
    </form>
  );
}

// ─── Step 2 — password setup ────────────────────────────────────

interface PasswordStepProps {
  email: string;
  error: ActivationError | null;
  submitting: boolean;
  canGoBack: boolean;
  onSubmit: (password: string) => Promise<void>;
  onBack: () => void;
}

function PasswordStep({
  email,
  error,
  submitting,
  canGoBack,
  onSubmit,
  onBack,
}: PasswordStepProps) {
  const [password, setPasswordValue] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const rules = useMemo(() => evaluatePassword(password), [password]);
  const allRulesPassed = rules.every((r) => r.passed);
  const passwordsMatch = password.length > 0 && password === confirm;
  const canSubmit = allRulesPassed && passwordsMatch;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!passwordsMatch) {
      setConfirmError("Las contraseñas no coinciden.");
      return;
    }
    setConfirmError(null);
    void onSubmit(password);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-teal-muted)]">
          <ShieldCheck
            className="h-5 w-5 text-[color:var(--text-teal)]"
            weight="duotone"
            aria-hidden="true"
          />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-[color:var(--text-primary)]">
            Crea tu contraseña
          </h1>
          <p className="text-[13px] text-[color:var(--text-secondary)]">
            Será tu contraseña permanente para{" "}
            <span className="font-medium text-[color:var(--text-primary)]">{email}</span>.
          </p>
        </div>
      </div>

      {error && (
        <Alert variant="error">
          <AlertTitle>{ERROR_COPY[error].title}</AlertTitle>
          <AlertDescription>{ERROR_COPY[error].body}</AlertDescription>
        </Alert>
      )}

      <Field label="Nueva contraseña" htmlFor="new-password" required>
        <div className="relative">
          <Input
            id="new-password"
            type={show ? "text" : "password"}
            value={password}
            onChange={(e) => setPasswordValue(e.target.value)}
            autoComplete="new-password"
            autoFocus
            className="pr-12"
          />
          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            aria-label={show ? "Ocultar contraseña" : "Mostrar contraseña"}
            className="absolute inset-y-0 right-0 flex w-12 items-center justify-center text-[color:var(--text-tertiary)] hover:text-[color:var(--text-primary)]"
          >
            {show ? (
              <EyeSlash className="h-4 w-4" weight="bold" aria-hidden="true" />
            ) : (
              <Eye className="h-4 w-4" weight="bold" aria-hidden="true" />
            )}
          </button>
        </div>
      </Field>

      <ul className="grid gap-2 sm:grid-cols-2" aria-label="Requisitos de la contraseña">
        {rules.map(({ rule, passed }) => (
          <li
            key={rule.label}
            className={
              "flex items-center gap-2 rounded-sm border px-3 py-2 text-xs " +
              (passed
                ? "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
                : "border-[color:var(--border-subtle)] bg-[color:var(--surface-sunken)] text-[color:var(--text-secondary)]")
            }
          >
            {passed ? (
              <Check className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
            ) : (
              <span className="h-3.5 w-3.5 rounded-full border border-current opacity-50" aria-hidden="true" />
            )}
            <span>{rule.label}</span>
          </li>
        ))}
      </ul>

      <Field
        label="Confirma tu contraseña"
        htmlFor="confirm-password"
        required
        error={confirmError}
      >
        <Input
          id="confirm-password"
          type={show ? "text" : "password"}
          value={confirm}
          onChange={(e) => {
            setConfirm(e.target.value);
            setConfirmError(null);
          }}
          autoComplete="new-password"
        />
      </Field>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {canGoBack ? (
          <Button type="button" variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
            Atrás
          </Button>
        ) : (
          <span className="text-xs text-[color:var(--text-tertiary)]">
            Tu invitación quedó verificada — continúa con tu contraseña.
          </span>
        )}
        <Button
          type="submit"
          loading={submitting}
          size="lg"
          disabled={!canSubmit && !submitting}
          className="sm:w-auto"
        >
          <span>Guardar contraseña</span>
          {!submitting && <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />}
        </Button>
      </div>
    </form>
  );
}

// ─── Step 3 — identity ──────────────────────────────────────────

interface IdentityStepProps {
  email: string;
  inference: EmailInference;
  presetCompany: string | null;
  presetRole: InvitationRole;
  error: ActivationError | null;
  submitting: boolean;
  onSubmit: (payload: {
    first_name: string;
    last_name: string;
    email: string;
    company: string;
    role: InvitationRole;
  }) => Promise<void>;
  onBack: () => void;
}

function IdentityStep({
  email,
  inference,
  presetCompany,
  presetRole,
  error,
  submitting,
  onSubmit,
  onBack,
}: IdentityStepProps) {
  const [firstName, setFirstName] = useState(inference.first_name);
  const [lastName, setLastName] = useState(inference.last_name);
  const [company, setCompany] = useState(presetCompany ?? inference.company);
  const [role, setRole] = useState<InvitationRole>(presetRole);
  const [companyTouched, setCompanyTouched] = useState(false);
  const [errors, setErrors] = useState<{
    first_name?: string;
    last_name?: string;
    company?: string;
  }>({});

  const companyAutoSuggested =
    presetCompany !== null ||
    (!inference.is_generic_domain && inference.company !== "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next: typeof errors = {};
    if (firstName.trim().length < 1) next.first_name = "Captura tu nombre.";
    if (lastName.trim().length < 1) next.last_name = "Captura tu apellido.";
    if (company.trim().length < 2)
      next.company = "Captura el nombre completo de tu empresa.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    void onSubmit({
      first_name: firstName.trim(),
      last_name: lastName.trim(),
      email,
      company: company.trim(),
      role,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
      <div className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[color:var(--surface-brand-muted)]">
          <UserCircle
            className="h-5 w-5 text-[color:var(--text-brand)]"
            weight="duotone"
            aria-hidden="true"
          />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-[color:var(--text-primary)]">
            ¿Quién está activando esta cuenta?
          </h1>
          <p className="text-[13px] text-[color:var(--text-secondary)]">
            Usaremos estos datos para personalizar tu portal.
          </p>
        </div>
      </div>

      {error && (
        <Alert variant="error">
          <AlertTitle>{ERROR_COPY[error].title}</AlertTitle>
          <AlertDescription>{ERROR_COPY[error].body}</AlertDescription>
        </Alert>
      )}

      <fieldset>
        <legend className="mb-2 text-[13px] font-medium text-[color:var(--text-primary)]">
          Confirma tu rol
        </legend>
        <div role="radiogroup" className="grid gap-2 sm:grid-cols-2">
          {(["provider", "client"] as const).map((value) => {
            const IconComponent: Icon = value === "client" ? Buildings : Truck;
            const isSelected = role === value;
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={isSelected}
                onClick={() => setRole(value)}
                className={cn(
                  "flex items-start gap-3 rounded-lg border px-3 py-3 text-left transition-colors duration-fast",
                  isSelected
                    ? "border-[color:var(--border-brand)] bg-[color:var(--surface-brand-muted)]"
                    : "border-[color:var(--border-default)] bg-[color:var(--surface-raised)] hover:border-[color:var(--border-strong)]",
                )}
              >
                <span
                  className={cn(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
                    isSelected
                      ? "bg-[color:var(--surface-brand)] text-[color:var(--text-inverse)]"
                      : "bg-[color:var(--surface-teal-muted)] text-[color:var(--text-teal)]",
                  )}
                  aria-hidden="true"
                >
                  <IconComponent className="h-4 w-4" weight="duotone" />
                </span>
                <div>
                  <p
                    className={cn(
                      "text-[13px] font-semibold",
                      isSelected
                        ? "text-[color:var(--text-brand)]"
                        : "text-[color:var(--text-primary)]",
                    )}
                  >
                    {value === "client" ? "Cliente" : "Proveedor"}
                  </p>
                  <p className="text-[11px] leading-4 text-[color:var(--text-secondary)]">
                    {value === "client"
                      ? "Reviso a mis proveedores REPSE."
                      : "Cargo mi expediente y obligaciones."}
                  </p>
                </div>
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Nombre"
          htmlFor="identity-first-name"
          required
          error={errors.first_name}
          helper={
            inference.first_name && firstName === inference.first_name
              ? "Lo sugerimos por tu correo. Corrige si no es correcto."
              : undefined
          }
        >
          <Input
            id="identity-first-name"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            autoComplete="given-name"
            placeholder="Juan"
          />
        </Field>

        <Field
          label="Apellido"
          htmlFor="identity-last-name"
          required
          error={errors.last_name}
        >
          <Input
            id="identity-last-name"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            autoComplete="family-name"
            placeholder="Pérez"
          />
        </Field>

        <Field label="Correo" htmlFor="identity-email" className="sm:col-span-2">
          <Input
            id="identity-email"
            value={email}
            disabled
            className="bg-[color:var(--surface-sunken)] text-[color:var(--text-tertiary)]"
          />
        </Field>

        <Field
          label="Empresa"
          htmlFor="identity-company"
          required
          error={errors.company}
          className="sm:col-span-2"
          helper={
            companyAutoSuggested && !companyTouched ? (
              <span className="inline-flex items-center gap-1.5">
                <Warning
                  className="h-3 w-3 text-[color:var(--text-teal)]"
                  weight="fill"
                  aria-hidden="true"
                />
                {presetCompany
                  ? "Tu cliente registró esta empresa en la invitación. Confírmala o corrígela."
                  : "Detectamos esta empresa por tu correo. Confírmala o corrígela."}
              </span>
            ) : inference.is_generic_domain && !presetCompany ? (
              "Captura el nombre legal completo de la empresa que representas."
            ) : undefined
          }
        >
          <Input
            id="identity-company"
            value={company}
            onChange={(e) => {
              setCompany(e.target.value);
              setCompanyTouched(true);
            }}
            autoComplete="organization"
            placeholder="Constructora ABC, S.A. de C.V."
          />
        </Field>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" weight="bold" aria-hidden="true" />
          Atrás
        </Button>
        <Button type="submit" loading={submitting} size="lg">
          <span>Entrar a CheckWise</span>
          {!submitting && <ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />}
        </Button>
      </div>
    </form>
  );
}

// ─── Step 4 — success ────────────────────────────────────────────

function SuccessStep() {
  return (
    <div className="flex flex-col items-center gap-4 py-6 text-center">
      <span
        className="cw-success-ring flex h-16 w-16 items-center justify-center rounded-full bg-[color:var(--status-success-bg)] text-[color:var(--status-success-text)]"
        aria-hidden="true"
      >
        <CheckCircle className="h-9 w-9" weight="fill" />
      </span>
      <div>
        <h1 className="text-xl font-semibold text-[color:var(--text-primary)]">
          Tu cuenta está lista
        </h1>
        <p className="mt-1 text-[13px] text-[color:var(--text-secondary)]">
          Te estamos llevando a tu expediente inicial para comenzar el proceso.
        </p>
      </div>
    </div>
  );
}
