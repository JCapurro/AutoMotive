/** public.my_bonus_trial(): the extra 7-day trial as /app/bonus shows it. */
export type BonusTrial = { state: "active" | "available" | "unavailable"; endsAt: string | null };

export function bonusTrial(value: unknown): BonusTrial {
  const v = value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  const state = v.state === "active" || v.state === "available" ? v.state : "unavailable";
  return { state, endsAt: state === "active" && typeof v.ends_at === "string" ? v.ends_at : null };
}
