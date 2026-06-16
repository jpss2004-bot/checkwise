"use client";

import { useState } from "react";
import { CheckCircle } from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";
import { submitContactRequest } from "@/lib/api/contact";

type FormState = "idle" | "loading" | "success" | "error";

const INPUT =
  "w-full rounded-xl bg-white/[0.07] border border-white/15 px-4 py-2.5 text-[13.5px] text-white placeholder:text-white/35 outline-none focus:border-[hsl(var(--teal-400))] focus:ring-1 focus:ring-[hsl(var(--teal-400)_/_.35)] transition-[border-color,box-shadow] duration-150";

export function ContactForm({ source = "demo-cta" }: { source?: string }) {
  const [state, setState] = useState<FormState>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const name = (fd.get("name") as string).trim();
    const email = (fd.get("email") as string).trim();
    const company = ((fd.get("company") as string) ?? "").trim();

    setState("loading");
    setErrorMsg(null);

    const result = await submitContactRequest({
      name,
      email,
      company,
      interest: "client_admin",
      source,
      message: company
        ? `Empresa: ${company}. Quiero conocer CheckWise.`
        : "Quiero conocer CheckWise.",
    });

    if (result.ok) {
      setState("success");
    } else {
      setState("error");
      setErrorMsg(result.error);
    }
  }

  if (state === "success") {
    return (
      <div className="flex flex-col items-center gap-3 py-4 text-center">
        <CheckCircle
          className="h-9 w-9 text-[hsl(var(--teal-300))]"
          weight="duotone"
          aria-hidden="true"
        />
        <p className="font-display text-[15px] font-semibold text-white">
          ¡Listo! Te contactamos pronto.
        </p>
        <p className="text-[12.5px] text-[hsl(var(--navy-200))]">
          Respondemos el mismo día hábil desde CDMX.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2.5">
      <input
        name="name"
        type="text"
        required
        placeholder="Nombre"
        disabled={state === "loading"}
        className={INPUT}
      />
      <input
        name="email"
        type="email"
        required
        placeholder="Correo"
        disabled={state === "loading"}
        className={INPUT}
      />
      <input
        name="company"
        type="text"
        placeholder="Empresa (opcional)"
        disabled={state === "loading"}
        className={INPUT}
      />
      {errorMsg ? (
        <p role="alert" className="text-[11.5px] text-red-400">
          {errorMsg}
        </p>
      ) : null}
      <Button
        type="submit"
        size="lg"
        disabled={state === "loading"}
        className="mt-0.5 w-full justify-center rounded-full border border-white/20 bg-white/10 text-white hover:bg-white/15 disabled:opacity-50"
      >
        {state === "loading" ? "Enviando…" : "Enviar mensaje"}
      </Button>
    </form>
  );
}
