"use client";

import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  ArrowRight,
  Plus,
} from "@phosphor-icons/react";

import { FAQ_ITEMS } from "@/lib/marketing/faq";

import { Eyebrow, Section, SectionTitle } from "./_shared";

const CATEGORIES = [
  {
    key: "repse" as const,
    label: "REPSE",
    caption: "La norma",
    items: FAQ_ITEMS.slice(0, 5),
  },
  {
    key: "checkwise" as const,
    label: "CheckWise",
    caption: "El producto",
    items: FAQ_ITEMS.slice(5),
  },
];

type CatKey = "repse" | "checkwise";

const EASE = [0.16, 1, 0.3, 1] as const;

export function V2Faq() {
  const reduced = useReducedMotion();
  const [cat, setCat] = useState<CatKey>("repse");
  const [idx, setIdx] = useState(0);

  const category = CATEGORIES.find((c) => c.key === cat)!;
  const items = category.items;
  const active = items[idx];
  const next = items[idx + 1] ?? null;

  function switchCat(key: CatKey) {
    setCat(key);
    setIdx(0);
  }

  return (
    <Section id="faq" band="page">
      <div className="text-center">
        <Eyebrow>Preguntas frecuentes</Eyebrow>
        <SectionTitle accent="explicados sin rodeos." className="mx-auto mt-4 text-center">
          REPSE y CheckWise,
        </SectionTitle>
      </div>

      {/* ── Desktop: two-panel reader ── */}
      <div className="mx-auto mt-14 hidden max-w-[1060px] overflow-hidden rounded-2xl border border-[color:var(--border-default)] shadow-[var(--shadow-md)] lg:grid lg:grid-cols-[272px_1fr]">
        {/* Left — question list */}
        <div className="flex flex-col border-r border-[color:var(--border-default)] bg-[color:var(--surface-raised)]">
          {/* Category tabs */}
          <div className="grid grid-cols-2 border-b border-[color:var(--border-default)]">
            {CATEGORIES.map((c) => {
              const on = c.key === cat;
              return (
                <button
                  key={c.key}
                  type="button"
                  onClick={() => switchCat(c.key)}
                  className={`py-4 text-[13px] font-semibold transition-colors ${
                    on
                      ? "bg-[color:var(--surface-page)] text-[color:var(--text-primary)] shadow-[inset_0_-2px_0_hsl(var(--teal-400))]"
                      : "text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)]"
                  }`}
                >
                  {c.label}
                  <span className={`ml-1.5 font-mono text-[10px] font-normal ${on ? "text-[color:var(--text-teal)]" : "text-[color:var(--text-tertiary)]"}`}>
                    {c.caption}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Question items */}
          <ol className="flex-1 py-1">
            {items.map((item, i) => {
              const on = i === idx;
              return (
                <li key={item.question}>
                  <button
                    type="button"
                    onClick={() => setIdx(i)}
                    className={`relative flex w-full items-start gap-3 border-l-2 px-5 py-3.5 text-left transition-colors ${
                      on
                        ? "border-l-[hsl(var(--teal-400))] bg-[hsl(var(--teal-500)/0.07)] text-[color:var(--text-primary)]"
                        : "border-l-transparent text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-page)] hover:text-[color:var(--text-primary)]"
                    }`}
                  >
                    <span className={`mt-px shrink-0 font-mono text-[10px] ${on ? "text-[color:var(--text-teal)]" : "text-[color:var(--text-tertiary)]"}`}>
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className={`text-[13px] leading-[1.45] ${on ? "font-semibold" : "font-medium"}`}>
                      {item.question}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>

          {/* Footer counter */}
          <div className="border-t border-[color:var(--border-default)] px-5 py-3">
            <p className="font-mono text-[10.5px] text-[color:var(--text-tertiary)]">
              {idx + 1} de {items.length} — {category.label}
            </p>
          </div>
        </div>

        {/* Right — answer display */}
        <div className="flex flex-col bg-[color:var(--surface-page)] p-10">
          <motion.div
            key={`${cat}-${idx}`}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: reduced ? 0 : 0.32, ease: EASE }}
            className="flex-1"
          >
            <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-[color:var(--text-teal)]">
              {category.caption}
            </span>
            <h3 className="font-display mt-3 text-[22px] font-bold leading-[1.2] tracking-[-0.01em] text-[color:var(--text-primary)]">
              {active.question}
            </h3>
            <p className="mt-5 text-[15.5px] leading-[1.75] text-[color:var(--text-secondary)]">
              {active.answer}
            </p>
          </motion.div>

          {next ? (
            <button
              type="button"
              onClick={() => setIdx(idx + 1)}
              className="group mt-10 flex items-center gap-2 self-start"
            >
              <span className="text-[12px] font-medium uppercase tracking-[0.12em] text-[color:var(--text-tertiary)] transition-colors group-hover:text-[color:var(--text-secondary)]">
                Siguiente
              </span>
              <ArrowRight
                className="h-3 w-3 text-[color:var(--text-tertiary)] transition-all group-hover:translate-x-0.5 group-hover:text-[color:var(--text-teal)]"
                weight="bold"
                aria-hidden="true"
              />
              <span className="max-w-[40ch] truncate text-[13.5px] font-medium text-[color:var(--text-secondary)] transition-colors group-hover:text-[color:var(--text-primary)]">
                {next.question}
              </span>
            </button>
          ) : (
            <a
              href="#contacto"
              className="group mt-10 inline-flex items-center gap-2 self-start rounded-full border border-[hsl(var(--teal-500)/0.4)] bg-[hsl(var(--teal-500)/0.06)] px-5 py-2.5 text-[13.5px] font-semibold text-[color:var(--text-teal)] transition-colors hover:bg-[hsl(var(--teal-500)/0.12)]"
            >
              Solicitar demo
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" weight="bold" aria-hidden="true" />
            </a>
          )}
        </div>
      </div>

      {/* ── Mobile: categorized accordion ── */}
      <div className="mx-auto mt-10 max-w-[680px] lg:hidden">
        {/* Category pills */}
        <div className="mb-6 grid grid-cols-2 gap-2">
          {CATEGORIES.map((c) => {
            const on = c.key === cat;
            return (
              <button
                key={c.key}
                type="button"
                onClick={() => switchCat(c.key)}
                className={`rounded-xl border py-3 text-[14px] font-semibold transition-colors ${
                  on
                    ? "border-[hsl(var(--teal-500)/0.5)] bg-[hsl(var(--teal-500)/0.07)] text-[color:var(--text-teal)]"
                    : "border-[color:var(--border-default)] text-[color:var(--text-secondary)]"
                }`}
              >
                {c.label}
                <span className="ml-1.5 font-mono text-[10px] font-normal opacity-70">
                  {c.caption}
                </span>
              </button>
            );
          })}
        </div>

        {/* Accordions */}
        <div className="flex flex-col gap-3">
          {items.map((f) => (
            <details
              key={f.question}
              className="cw-faq group rounded-2xl border border-[color:var(--border-default)] bg-[color:var(--surface-raised)] p-5 open:shadow-[var(--shadow-sm)]"
            >
              <summary className="flex cursor-pointer list-none items-start justify-between gap-4">
                <h3 className="font-display text-[15.5px] font-semibold leading-[1.35] text-[color:var(--text-primary)]">
                  {f.question}
                </h3>
                <Plus
                  className="mt-0.5 h-4 w-4 shrink-0 text-[color:var(--text-teal)] transition-transform duration-200 group-open:rotate-45"
                  weight="bold"
                  aria-hidden="true"
                />
              </summary>
              <p className="mt-3 text-[14px] leading-[1.65] text-[color:var(--text-secondary)]">
                {f.answer}
              </p>
            </details>
          ))}
        </div>
      </div>
    </Section>
  );
}
