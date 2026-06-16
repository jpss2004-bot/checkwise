"use client";

import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowRight, ArrowUpRight, Plus } from "@phosphor-icons/react";

import { FAQ_ITEMS } from "@/lib/marketing/faq";

import { Eyebrow, Section, SectionTitle } from "./_shared";

const CATEGORIES = [
  { key: "repse" as const, label: "Sobre REPSE", items: FAQ_ITEMS.slice(0, 5) },
  { key: "checkwise" as const, label: "Sobre CheckWise", items: FAQ_ITEMS.slice(5) },
];

type CatKey = "repse" | "checkwise";

const ENTER = { duration: 0.52, ease: [0.22, 1, 0.36, 1] } as const;
const EXIT  = { duration: 0.18, ease: [0.4, 0, 1, 1]    } as const;

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
      {/* Header */}
      <div className="text-center">
        <Eyebrow>Preguntas frecuentes</Eyebrow>
        <SectionTitle accent="explicados sin rodeos." className="mx-auto mt-4 text-center">
          REPSE y CheckWise,
        </SectionTitle>
      </div>

      {/* Category selector — floats above the card */}
      <div className="mt-10 flex justify-center gap-1.5">
        {CATEGORIES.map((c) => {
          const on = c.key === cat;
          return (
            <button
              key={c.key}
              type="button"
              onClick={() => switchCat(c.key)}
              className={`rounded-full px-5 py-2 text-[13.5px] font-semibold transition-all duration-200 ${
                on
                  ? "bg-[hsl(var(--teal-500)/0.1)] text-[color:var(--text-teal)]"
                  : "text-[color:var(--text-tertiary)] hover:text-[color:var(--text-secondary)]"
              }`}
            >
              {c.label}
            </button>
          );
        })}
      </div>

      {/* ── Desktop: two-panel reader ── */}
      <div className="mx-auto mt-5 hidden max-w-[1060px] overflow-hidden rounded-3xl shadow-[0_4px_32px_-8px_rgba(3,20,31,0.13),0_1px_8px_-2px_rgba(3,20,31,0.07)] lg:grid lg:grid-cols-[258px_1fr]">

        {/* Left — question list */}
        <div className="flex flex-col border-r border-[color:var(--border-default)] bg-[color:var(--surface-raised)]">
          <ol className="flex-1 space-y-0.5 p-3">
            {items.map((item, i) => {
              const on = i === idx;
              return (
                <li key={item.question}>
                  <button
                    type="button"
                    onClick={() => setIdx(i)}
                    className={`flex w-full items-start gap-3 rounded-xl px-3.5 py-3 text-left transition-all duration-200 ${
                      on
                        ? "bg-[color:var(--surface-page)] text-[color:var(--text-primary)] shadow-[0_1px_6px_-1px_rgba(0,0,0,0.08),0_0_0_1px_rgba(0,0,0,0.04)]"
                        : "text-[color:var(--text-secondary)] hover:bg-[color:var(--surface-page)] hover:text-[color:var(--text-primary)] hover:opacity-80"
                    }`}
                  >
                    <span
                      className={`mt-px shrink-0 font-mono text-[10px] ${on ? "text-[color:var(--text-teal)]" : "text-[color:var(--text-tertiary)]"}`}
                    >
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

          <div className="border-t border-[color:var(--border-default)] px-6 py-3">
            <p className="font-mono text-[10px] text-[color:var(--text-tertiary)]">
              {idx + 1} / {items.length} — {category.label}
            </p>
          </div>
        </div>

        {/* Right — answer pane */}
        <div className="flex min-h-[420px] flex-col bg-[color:var(--surface-page)] p-12">
          <AnimatePresence mode="wait">
            <motion.div
              key={`${cat}-${idx}`}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8, transition: reduced ? { duration: 0 } : EXIT }}
              transition={reduced ? { duration: 0 } : ENTER}
              className="flex flex-1 flex-col"
            >
              {/* Question */}
              <h3 className="font-display text-[25px] font-bold leading-[1.18] tracking-[-0.02em] text-[color:var(--text-primary)]">
                {active.question}
              </h3>

              {/* Answer */}
              <p className="mt-6 text-[16.5px] leading-[1.8] text-[color:var(--text-secondary)]">
                {active.answer}
              </p>

              {/* Contextual deep-link into sub-page */}
              {active.learnMore && (
                <a
                  href={active.learnMore.href}
                  className="group mt-7 flex w-fit items-center gap-2 rounded-xl border border-[hsl(var(--teal-500)/0.22)] bg-[hsl(var(--teal-500)/0.05)] px-4 py-2.5 transition-all duration-200 hover:border-[hsl(var(--teal-500)/0.4)] hover:bg-[hsl(var(--teal-500)/0.09)]"
                >
                  <span className="text-[13px] font-semibold text-[color:var(--text-teal)]">
                    {active.learnMore.label}
                  </span>
                  <ArrowUpRight
                    className="h-3.5 w-3.5 text-[color:var(--text-teal)] transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
                    weight="bold"
                    aria-hidden="true"
                  />
                </a>
              )}

              {/* Footer nav */}
              <div className="mt-auto pt-10">
                {next ? (
                  <button
                    type="button"
                    onClick={() => setIdx(idx + 1)}
                    className="group flex items-center gap-2.5"
                  >
                    <span className="text-[11px] font-medium uppercase tracking-[0.15em] text-[color:var(--text-tertiary)] transition-colors group-hover:text-[color:var(--text-secondary)]">
                      Siguiente
                    </span>
                    <ArrowRight
                      className="h-3 w-3 text-[color:var(--text-tertiary)] transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-[color:var(--text-teal)]"
                      weight="bold"
                      aria-hidden="true"
                    />
                    <span className="max-w-[38ch] truncate text-[13.5px] font-medium text-[color:var(--text-secondary)] transition-colors group-hover:text-[color:var(--text-primary)]">
                      {next.question}
                    </span>
                  </button>
                ) : (
                  <a
                    href="#contacto"
                    className="group inline-flex items-center gap-2 rounded-full border border-[hsl(var(--teal-500)/0.4)] bg-[hsl(var(--teal-500)/0.06)] px-5 py-2.5 text-[13.5px] font-semibold text-[color:var(--text-teal)] transition-colors hover:bg-[hsl(var(--teal-500)/0.12)]"
                  >
                    Solicitar demo
                    <ArrowRight
                      className="h-3.5 w-3.5 transition-transform duration-200 group-hover:translate-x-0.5"
                      weight="bold"
                      aria-hidden="true"
                    />
                  </a>
                )}
              </div>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>

      {/* ── Mobile: accordion ── */}
      <div className="mx-auto mt-10 max-w-[680px] lg:hidden">
        {/* Category pills */}
        <div className="mb-6 flex gap-2">
          {CATEGORIES.map((c) => {
            const on = c.key === cat;
            return (
              <button
                key={c.key}
                type="button"
                onClick={() => switchCat(c.key)}
                className={`flex-1 rounded-2xl border py-3 text-[14px] font-semibold transition-all duration-200 ${
                  on
                    ? "border-[hsl(var(--teal-500)/0.4)] bg-[hsl(var(--teal-500)/0.07)] text-[color:var(--text-teal)]"
                    : "border-[color:var(--border-default)] text-[color:var(--text-secondary)]"
                }`}
              >
                {c.label}
              </button>
            );
          })}
        </div>

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
              <div className="mt-3">
                <p className="text-[14px] leading-[1.65] text-[color:var(--text-secondary)]">
                  {f.answer}
                </p>
                {f.learnMore && (
                  <a
                    href={f.learnMore.href}
                    className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-semibold text-[color:var(--text-teal)] hover:underline"
                  >
                    {f.learnMore.label}
                    <ArrowUpRight className="h-3 w-3" weight="bold" aria-hidden="true" />
                  </a>
                )}
              </div>
            </details>
          ))}
        </div>
      </div>
    </Section>
  );
}
