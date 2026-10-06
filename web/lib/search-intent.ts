import { ASSISTED_MAX_CHARS } from "@/lib/assisted";

/** The destination travels through password login, Google and email confirmation. */
export function searchStartHref(signedIn: boolean, text = ""): string {
  const prompt = text.trim();
  const next = prompt
    ? `/app/searches/new?${new URLSearchParams({ prompt })}`
    : "/app/searches/new";
  if (signedIn) return next;
  return prompt ? `/login?${new URLSearchParams({ next })}` : "/login?next=/app/searches/new";
}

export function searchIntentPrompt(value: string | string[] | undefined): string {
  return typeof value === "string" && value.length <= ASSISTED_MAX_CHARS ? value.trim() : "";
}
