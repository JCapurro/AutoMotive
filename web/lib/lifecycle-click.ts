/**
 * /m/<id>: the button of a plan email (docs/MAILS_DE_PLAN.md). The click is
 * recorded with public.track_lifecycle_click (lifecycle_email_clicked) and
 * leads to the email's target, an Ese Auto path fixed when it was claimed.
 * Link previews and HEAD requests are redirected without counting.
 */

export function lifecycleEmailId(value: string): number | null {
  return /^\d{1,15}$/.test(value) ? Number(value) : null;
}

/** Only a path of this site, whatever the ledger holds: never another host. */
export function lifecycleTarget(value: unknown): string | null {
  return typeof value === "string" && /^\/(?![/\\])/.test(value) ? value : null;
}
