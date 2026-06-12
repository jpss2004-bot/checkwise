# UX routing and button audit - 2026-06-12

Scope: provider platform, admin reviewer/Bandeja flow, admin provider expediente, client provider overview/detail, client calendar, and shared PDF preview/download behavior.

## Issues fixed in this slice

| Area | Location | Current behavior | Expected behavior | Fix |
| --- | --- | --- | --- | --- |
| Provider Wise assistant | `components/checkwise/portal/wise-dock.tsx` | Wise opened from the bottom-right, competing with review/upload/download CTAs and the feedback launcher. | Wise should be accessible without blocking primary actions. | Anchored Wise bottom-left. On desktop provider pages it offsets past the sidebar; on tablet/mobile it stays bottom-left and opens as the existing bottom sheet. |
| Provider submission detail | `app/portal/submissions/[submission_id]/page.tsx` | Buttons labeled "Calendario" and "Volver al calendario" routed to `/portal/dashboard`. | Calendar-labeled actions should return to the calendar. | Repointed calendar CTAs to `/portal/calendar`; left dashboard links only where the label says dashboard/inicio. |
| Provider upload success | `components/checkwise/intake-wizard.tsx` | The default "Ver mi calendario" success CTA routed to dashboard. | After upload, "Ver mi calendario" should open the calendar. | Repointed the success CTA to `/portal/calendar`. |
| Provider PDF preview/download | `api/v1/portal.py`, `lib/api/portal.ts`, provider detail | Preview could fail when API redirected to presigned storage and browser CORS/cookie behavior blocked the Blob fetch. Download relied on top-level cookie navigation. | Preview/download should use the same authenticated app session reliably. | Added `?proxy=1` to provider document streaming and made preview/download fetch bytes through the API Blob path. |
| Admin Bandeja filters | `app/admin/reviewer/page.tsx`, reviewer detail | Queue filters were URL-backed, but opening a document dropped the return context. | Returning from detail should restore selected provider/client/status/RFC/risk filters. | Detail links now include safe `returnTo=/admin/reviewer?...`; reviewer detail uses that for header, decision-complete, keyboard next, lineage, and previous attempts. |
| Admin provider expediente | `app/admin/vendors/[vendor_id]/page.tsx` | Back to providers lost `client_id`; document links opened reviewer detail with no origin context. | Provider detail should preserve client scope and return to the provider expediente when opened from there. | Back link preserves `client_id`; reviewer links include `returnTo` for the vendor expediente. |
| Client provider list/detail | `app/client/vendors/page.tsx`, `app/client/vendors/[vendor_id]/page.tsx` | Search/semaphore filters were local-only; explicit "Volver" lost list context. | Selected list context should survive opening a provider and returning. | List filters now mirror to URL; provider detail consumes safe `returnTo` and labels the back action based on source. |
| Client calendar/detail | `app/client/calendar/page.tsx` | Year/provider calendar filters were local-only; provider detail opened from calendar returned to provider list. | Calendar scope should persist and provider detail should return to the calendar when that was the source. | Calendar year/vendor filters mirror to URL; "Ver expediente" passes `returnTo` to provider detail. |
| Client contract document buttons | `app/client/vendors/[vendor_id]/page.tsx`, `api/v1/client.py`, `lib/api/client.ts` | Contract download used a plain anchor that cannot carry the staff bearer token; preview had the same storage redirect risk. | View/download should be authenticated and reliable. | Added client document `?proxy=1`; view/download now use authenticated Blob fetches with loading/error states. |

## Follow-up recommendations

- Extend the same `returnTo` pattern to report-editor and notification deep links where users jump into a report/document from filtered lists.
- Add Playwright coverage for "filter list -> open detail -> return" across admin reviewer and client providers.
- Consider turning client/provider list filters into explicit "applied filter" state if live URL updates while typing feel too chatty.
