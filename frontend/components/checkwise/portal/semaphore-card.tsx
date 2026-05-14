import { CheckCircle, Warning, WarningOctagon, type Icon } from "@phosphor-icons/react";

import { Progress } from "@/components/ui/progress";
import type { DashboardSemaphore, SemaphoreTone } from "@/lib/mock/dashboard";

const TONE_ICON: Record<SemaphoreTone, Icon> = {
  green: CheckCircle,
  yellow: Warning,
  red: WarningOctagon,
};

const TONE_RING: Record<SemaphoreTone, string> = {
  green: "bg-[color:var(--status-success-text)] text-white",
  yellow: "bg-[color:var(--status-warning-text)] text-white",
  red: "bg-[color:var(--status-error-text)] text-white",
};

const TONE_PROGRESS: Record<SemaphoreTone, "success" | "warning" | "error"> = {
  green: "success",
  yellow: "warning",
  red: "error",
};

const TONE_CARD: Record<SemaphoreTone, string> = {
  green: "border-[color:var(--status-success-border)] bg-[color:var(--status-success-bg)]",
  yellow: "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-bg)]",
  red: "border-[color:var(--status-error-border)] bg-[color:var(--status-error-bg)]",
};

const TONE_LABEL: Record<SemaphoreTone, string> = {
  green: "Verde · al día",
  yellow: "Amarillo · puntos por atender",
  red: "Rojo · obligaciones críticas",
};

interface SemaphoreCardProps {
  data: DashboardSemaphore;
}

/**
 * Compliance health "semáforo" hero card.
 *
 * Combines the tone (green/yellow/red), a plain-language headline,
 * a compliance % progress bar, and a 2-stat readout (on track /
 * tracked). Spec: docs/DESIGN_SYSTEM.md §6.2.
 */
export function SemaphoreCard({ data }: SemaphoreCardProps) {
  const IconComponent = TONE_ICON[data.tone];
  return (
    <section
      className={`cw-fade-up rounded-xl border p-6 shadow-sm sm:p-8 ${TONE_CARD[data.tone]}`}
      aria-label="Estado de cumplimiento"
    >
      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <div className="flex flex-1 items-start gap-4">
          <span
            className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full shadow-xs ${TONE_RING[data.tone]}`}
            aria-hidden="true"
          >
            <IconComponent className="h-8 w-8" weight="fill" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-mono text-[10px] uppercase tracking-wide text-[color:var(--text-tertiary)]">
              {TONE_LABEL[data.tone]}
            </p>
            <h1 className="mt-1 text-xl font-semibold leading-7 text-[color:var(--text-primary)]">
              {data.headline}
            </h1>
            <p className="mt-2 max-w-prose text-[13px] leading-5 text-[color:var(--text-secondary)]">
              {data.description}
            </p>
            <div className="mt-4 max-w-md">
              <Progress
                value={data.compliance_pct}
                label={`${data.on_track} de ${data.total_tracked} obligaciones al día`}
                showValue
                tone={TONE_PROGRESS[data.tone]}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
