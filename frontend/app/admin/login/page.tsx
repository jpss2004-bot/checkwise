"use client";

import { type FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Loader2, LogIn } from "lucide-react";

import { BrandLogo } from "@/components/checkwise/brand-logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthApiError, login } from "@/lib/api/auth";
import {
  readAdminSession,
  writeAdminSession,
} from "@/lib/session/admin";

export default function AdminLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (readAdminSession()) {
      router.replace("/admin");
    }
  }, [router]);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const session = await login(email, password);
      writeAdminSession(session);
      router.replace("/admin");
    } catch (err) {
      if (err instanceof AuthApiError && err.status === 401) {
        setError("Correo o contraseña incorrectos.");
      } else if (err instanceof AuthApiError && err.status === 422) {
        setError("Formato de correo inválido.");
      } else {
        setError("No pudimos iniciar sesión. Intenta de nuevo.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-5 py-10">
      <div className="mb-6 flex flex-col gap-2">
        <BrandLogo size="md" poweredBy />
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          Espacio interno
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Iniciar sesión</CardTitle>
          <p className="mt-1 text-sm text-muted-foreground">
            Acceso para personal autorizado de LegalShelf. Los proveedores
            siguen entrando con su sesión de portal.
          </p>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Correo</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@legalshelf.mx"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Contraseña</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error ? (
              <div
                role="alert"
                className="rounded-md border border-amber-300 bg-amber-50 p-3"
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle
                    className="mt-0.5 h-4 w-4 shrink-0 text-amber-600"
                    aria-hidden
                  />
                  <p className="text-sm text-amber-900">{error}</p>
                </div>
              </div>
            ) : null}

            <Button
              type="submit"
              className="w-full active:scale-[0.98]"
              disabled={submitting}
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <LogIn className="h-4 w-4" aria-hidden />
              )}
              {submitting ? "Verificando…" : "Entrar"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <p className="mt-4 text-center text-xs text-muted-foreground">
        ¿Eres proveedor? Entra desde la{" "}
        <Link className="underline" href="/">
          página principal
        </Link>
        .
      </p>
    </main>
  );
}
