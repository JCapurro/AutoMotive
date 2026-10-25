/** k=n: an alert (notifications); k=m: a plan email (lifecycle_emails). Anything else is ignored. */
export function openTarget(id: string, kind: string | null): { kind: "n" | "m"; id: number } | null {
  if (!/^\d{1,18}$/.test(id) || (kind !== "n" && kind !== "m")) return null;
  const n = Number(id);
  return Number.isSafeInteger(n) && n > 0 ? { kind, id: n } : null;
}
