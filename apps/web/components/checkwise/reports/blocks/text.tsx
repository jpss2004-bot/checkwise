"use client";

import { TextAa } from "@phosphor-icons/react";

import type { BlockDefinition, BlockProps } from "@/lib/reports/registry";

/**
 * Plain text block. Free-form intro paragraphs, transitions,
 * commentary. The canvas hands us a config with an optional heading
 * + the body text. We render directly with contentEditable so the
 * user can type inline.
 *
 * AI summary is supported (Phase 3.3) but rendered the same way —
 * the AI-pill annotation comes from a separate marker the canvas
 * places on the block container, not from this component.
 */

interface TextConfig {
  heading?: string;
  body: string;
}

export const textDefinition: Omit<BlockDefinition<TextConfig>, "Component"> = {
  type: "text",
  label: "Texto",
  icon: TextAa,
  description: "Párrafo libre para introducir o conectar secciones.",
  defaultConfig: { body: "" },
};

export function TextBlock({ block, editable, onPatch }: BlockProps<TextConfig>) {
  const { heading, body } = block.config;
  return (
    <div className="space-y-2 py-2">
      {(heading || editable) && (
        <input
          type="text"
          placeholder="Título de la sección (opcional)"
          value={heading ?? ""}
          disabled={!editable}
          onChange={(e) =>
            onPatch({ config: { ...block.config, heading: e.target.value } })
          }
          className="w-full border-0 bg-transparent p-0 text-base font-semibold text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--text-tertiary)] focus:ring-0 disabled:cursor-default"
        />
      )}
      <textarea
        placeholder={
          editable
            ? "Escribe el contenido aquí. Una a tres frases. No filler."
            : "—"
        }
        value={body}
        disabled={!editable}
        onChange={(e) =>
          onPatch({ config: { ...block.config, body: e.target.value } })
        }
        rows={Math.max(2, body.split("\n").length)}
        className="w-full resize-none border-0 bg-transparent p-0 text-[14px] leading-relaxed text-[color:var(--text-primary)] outline-none placeholder:text-[color:var(--text-tertiary)] focus:ring-0 disabled:cursor-default"
      />
    </div>
  );
}
