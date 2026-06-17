"use client";

import { useMemo } from "react";

import { Select } from "@/components/ui/select";

/**
 * Period picker (CW-12).
 *
 * The portal mints four canonical ``period_key`` formats (see
 * apps/api/app/core/period_range.py): ``YYYY-Mxx`` (month), ``YYYY-Bx``
 * (bimestre, x∈1..6), ``YYYY-Qx`` (cuatrimestre, x∈1..3) and ``YYYY-A``
 * (full fiscal year). The filter UIs used free-text inputs, so a provider
 * could only "search by bimestre/cuatrimestre" if they already knew the
 * code — and the help text didn't even mention cuatrimestres. This picker
 * turns the granularity into a first-class choice and emits the canonical
 * key, so every frequency is discoverable.
 */

type Granularity = "" | "M" | "B" | "Q" | "A";

const MONTHS_ES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
];
const BIMESTRE_LABELS = [
  "B1 · Ene–Feb",
  "B2 · Mar–Abr",
  "B3 · May–Jun",
  "B4 · Jul–Ago",
  "B5 · Sep–Oct",
  "B6 · Nov–Dic",
];
const CUATRIMESTRE_LABELS = ["Q1 · Ene–Abr", "Q2 · May–Ago", "Q3 · Sep–Dic"];

const GRANULARITY_LABEL: Record<Exclude<Granularity, "">, string> = {
  M: "Mes",
  B: "Bimestre",
  Q: "Cuatrimestre",
  A: "Año",
};

type Parsed = { gran: Granularity; year: number; idx: number };

function parsePeriodKey(value: string, fallbackYear: number): Parsed {
  const m = value.match(/^(\d{4})-M(\d{2})$/);
  if (m) return { gran: "M", year: Number(m[1]), idx: Number(m[2]) };
  const b = value.match(/^(\d{4})-B([1-6])$/);
  if (b) return { gran: "B", year: Number(b[1]), idx: Number(b[2]) };
  const q = value.match(/^(\d{4})-Q([1-3])$/);
  if (q) return { gran: "Q", year: Number(q[1]), idx: Number(q[2]) };
  const a = value.match(/^(\d{4})-A$/);
  if (a) return { gran: "A", year: Number(a[1]), idx: 0 };
  return { gran: "", year: fallbackYear, idx: 1 };
}

function buildPeriodKey(gran: Granularity, year: number, idx: number): string {
  switch (gran) {
    case "M":
      return `${year}-M${String(idx).padStart(2, "0")}`;
    case "B":
      return `${year}-B${idx}`;
    case "Q":
      return `${year}-Q${idx}`;
    case "A":
      return `${year}-A`;
    default:
      return "";
  }
}

/** A sensible default sub-period when switching granularity: the one that
 *  contains the current month, so the picker lands on "now" not "January". */
function defaultIdxFor(gran: Granularity, month: number): number {
  switch (gran) {
    case "M":
      return month;
    case "B":
      return Math.ceil(month / 2);
    case "Q":
      return Math.ceil(month / 4);
    default:
      return 1;
  }
}

function periodOptions(gran: Granularity): { value: number; label: string }[] {
  if (gran === "M")
    return MONTHS_ES.map((label, i) => ({ value: i + 1, label }));
  if (gran === "B")
    return BIMESTRE_LABELS.map((label, i) => ({ value: i + 1, label }));
  if (gran === "Q")
    return CUATRIMESTRE_LABELS.map((label, i) => ({ value: i + 1, label }));
  return [];
}

export function PeriodPicker({
  value,
  onChange,
  allowEmpty = true,
  className,
}: {
  /** Canonical period_key (or "" for no filter). */
  value: string;
  onChange: (periodKey: string) => void;
  /** Show a "Todos los periodos" option that emits "". Default true. */
  allowEmpty?: boolean;
  className?: string;
}) {
  const now = useMemo(() => new Date(), []);
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;
  const parsed = parsePeriodKey(value, currentYear);

  const years = useMemo(() => {
    const list: number[] = [];
    for (let y = currentYear + 1; y >= currentYear - 5; y--) list.push(y);
    if (!list.includes(parsed.year)) list.push(parsed.year);
    return list.sort((a, b) => b - a);
  }, [currentYear, parsed.year]);

  const opts = periodOptions(parsed.gran);

  return (
    <div className={`flex flex-wrap gap-2 ${className ?? ""}`}>
      <Select
        aria-label="Granularidad del periodo"
        value={parsed.gran}
        onChange={(e) => {
          const gran = e.target.value as Granularity;
          if (gran === "") {
            onChange("");
            return;
          }
          onChange(
            buildPeriodKey(gran, parsed.year, defaultIdxFor(gran, currentMonth)),
          );
        }}
      >
        {allowEmpty ? <option value="">Todos los periodos</option> : null}
        {(Object.keys(GRANULARITY_LABEL) as Exclude<Granularity, "">[]).map(
          (g) => (
            <option key={g} value={g}>
              {GRANULARITY_LABEL[g]}
            </option>
          ),
        )}
      </Select>

      {parsed.gran !== "" ? (
        <Select
          aria-label="Año del periodo"
          value={String(parsed.year)}
          onChange={(e) =>
            onChange(buildPeriodKey(parsed.gran, Number(e.target.value), parsed.idx))
          }
        >
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </Select>
      ) : null}

      {opts.length > 0 ? (
        <Select
          aria-label="Periodo"
          value={String(parsed.idx)}
          onChange={(e) =>
            onChange(
              buildPeriodKey(parsed.gran, parsed.year, Number(e.target.value)),
            )
          }
        >
          {opts.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </Select>
      ) : null}
    </div>
  );
}
