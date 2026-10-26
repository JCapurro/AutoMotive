/**
 * The reason links of the remarketing emails (docs/MAILS_DE_PLAN.md,
 * «Remarketing»): /f/<id>?r=<reason>&s=<signature>. Opening one records
 * nothing (mail scanners open every link); the page asks to confirm and lets
 * the person add a comment. The signature is the email's button one (scope
 * "m"): same email, same owner.
 */
import { alertLinkSecrets, validAlertLinkSignature } from "@/lib/alert-session";
import { REMARKETING_KINDS } from "@/lib/email-feedback-reasons";
import { createAdminClient } from "@/lib/supabase/admin";

/**
 * The sent remarketing email this link belongs to, or null. With
 * ALERT_LINK_SECRET the signature must check out; without it the worker
 * sends unsigned links, and those are taken as they come.
 */
export async function feedbackEmail(id: number, signature: string | null): Promise<{ kind: string; after: unknown } | null> {
  const { data } = await createAdminClient()
    .from("lifecycle_emails")
    .select("user_id, kind, status, payload")
    .eq("id", id)
    .maybeSingle();
  if (!data || data.status !== "sent" || !REMARKETING_KINDS.includes(data.kind)) return null;
  const secrets = alertLinkSecrets();
  if (secrets.length && !validAlertLinkSignature({ scope: "m", id, signature }, data.user_id, secrets)) return null;
  const payload = data.payload && typeof data.payload === "object" && !Array.isArray(data.payload) ? data.payload : {};
  return { kind: data.kind, after: (payload as Record<string, unknown>).after };
}
