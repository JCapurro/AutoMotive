/**
 * The reasons of the remarketing emails' links (docs/MAILS_DE_PLAN.md,
 * «Remarketing»): codes and labels are the worker's
 * (notifications/templates.py, FEEDBACK_REASONS). Pure: tests and pages import it.
 */
export const FEEDBACK_REASONS = {
  browsing: "Solo estaba mirando",
  missing_model: "No encontré mi modelo o versión",
  wrong_search: "La búsqueda que armaron no era lo que pedí",
  unclear: "No entendí qué hace Ese Auto",
  bought: "Ya compré un auto",
  other: "Otro motivo",
} as const;
export type FeedbackReason = keyof typeof FEEDBACK_REASONS;

export const FEEDBACK_COMMENT_MAX = 2000;
export const REMARKETING_KINDS = ["search_abandoned", "search_not_started", "search_feedback"];

export function feedbackReason(value: unknown): FeedbackReason | null {
  return typeof value === "string" && Object.hasOwn(FEEDBACK_REASONS, value) ? (value as FeedbackReason) : null;
}

export function feedbackEmailId(value: unknown): number | null {
  return typeof value === "string" && /^\d{1,15}$/.test(value) ? Number(value) : null;
}

export function feedbackComment(value: unknown): string | null {
  const text = typeof value === "string" ? value.trim().slice(0, FEEDBACK_COMMENT_MAX) : "";
  return text || null;
}

/** The reasons an email offers: wrong_search only after an assisted request (1A, or its follow-up). */
export function offeredReasons(kind: string, after: unknown): FeedbackReason[] {
  const asked = kind === "search_abandoned" || (kind === "search_feedback" && after === "search_abandoned");
  return (Object.keys(FEEDBACK_REASONS) as FeedbackReason[]).filter((r) => r !== "wrong_search" || asked);
}
