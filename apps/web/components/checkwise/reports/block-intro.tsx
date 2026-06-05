/**
 * BlockIntro — the in-document lead for a report block.
 *
 * 2026-06-05: reports were visual but terse — a reader landing on a
 * bare risk matrix or KPI band had to infer what they were looking at
 * and how to read the encoded scores/colors. BlockIntro gives each
 * data block a short, plain-language lead: an optional title and a
 * one-line caption that says what the block shows and how to read it.
 *
 * Unlike <BlockHeader> (editor-only authoring chrome that hides in
 * read-only/print), BlockIntro is part of the document — it renders in
 * the StoryView, the share view, and the printed PDF, so the context
 * travels with the deliverable.
 *
 * Presentational only. Copy is passed in by each block so the wording
 * lives next to the data it describes.
 */

export interface BlockIntroProps {
  /** Optional section title. Omit on blocks that already carry their
   *  own headline (e.g. the compliance_state semáforo) and only need
   *  the caption. */
  title?: string;
  /** One- to two-sentence plain-language caption: what this shows and
   *  how to read it. */
  caption: string;
}

export function BlockIntro({ title, caption }: BlockIntroProps) {
  return (
    <div className="space-y-1 print:break-inside-avoid">
      {title ? (
        <h3 className="text-[15px] font-semibold leading-tight tracking-tight text-[color:var(--text-primary)]">
          {title}
        </h3>
      ) : null}
      <p className="max-w-prose text-[12px] leading-relaxed text-[color:var(--text-secondary)]">
        {caption}
      </p>
    </div>
  );
}
