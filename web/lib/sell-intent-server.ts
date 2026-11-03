import "server-only";

import { alertLinkSecrets, validAlertLinkSignature } from "@/lib/alert-session";
import { currentUser } from "@/lib/auth";
import {
  answerRow,
  canAnswer,
  maskEmail,
  noticeRow,
  type SellIntentAnswer,
  type SellIntentConfig,
  type SellIntentSource,
} from "@/lib/sell-intent";
import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";
import type { Database } from "@/types/database";

/**
 * PAR-05, Prueba B: who answers on /vender-mi-auto. From the welcome email's
 * links (/vender-mi-auto?e=<lifecycle_email_id>&r=si|no&s=<signature>,
 * worker/notifications/links.py) it is that email's owner, without a session:
 * the service role writes, after checking the signature like /f/<id> does.
 * Otherwise it is the signed-in account, through RLS. Never an anonymous session.
 */
export type SellIntentViewer = {
  userId: string;
  /** The account's email as the page may show it: whole for a session or a signed link, masked otherwise. */
  email: string | null;
  link: { id: number; signature: string | null } | null;
};

export type SellIntentRow = Database["public"]["Tables"]["sell_intent"]["Row"];

/** The owner of a sent welcome email, when the link checks out (signed whenever ALERT_LINK_SECRET is set). */
export async function emailLinkViewer(id: number, signature: string | null): Promise<SellIntentViewer | null> {
  const admin = createAdminClient();
  const { data } = await admin.from("lifecycle_emails").select("user_id, kind, status").eq("id", id).maybeSingle();
  if (!data || data.status !== "sent" || data.kind !== "search_activated") return null;
  const secrets = alertLinkSecrets();
  const signed = secrets.length > 0 && validAlertLinkSignature({ scope: "m", id, signature }, data.user_id, secrets);
  if (secrets.length && !signed) return null;
  const { data: profile } = await admin.from("profiles").select("email").eq("id", data.user_id).maybeSingle();
  const email = profile?.email ?? null;
  return { userId: data.user_id, email: email && (signed ? email : maskEmail(email)), link: { id, signature } };
}

/** The signed-in account, if it may answer (it has an email). */
export async function sessionViewer(): Promise<SellIntentViewer | null> {
  const user = await currentUser();
  return user && canAnswer(user) ? { userId: user.id, email: user.email, link: null } : null;
}

export async function resolveViewer(id: number | null, signature: string | null): Promise<SellIntentViewer | null> {
  return id != null ? emailLinkViewer(id, signature) : sessionViewer();
}

/** The email link writes with the service role; a session writes its own row through RLS. */
async function clientFor(viewer: SellIntentViewer) {
  return viewer.link ? createAdminClient() : await createClient();
}

export async function currentAnswer(viewer: SellIntentViewer): Promise<SellIntentRow | null> {
  const { data } = await (await clientFor(viewer)).from("sell_intent").select("*").eq("user_id", viewer.userId).maybeSingle();
  return (data as SellIntentRow | null) ?? null;
}

/** Whether the signed-in account already answered (the ficha line hides then). */
export async function hasAnswered(userId: string): Promise<boolean> {
  const { data } = await (await createClient()).from("sell_intent").select("user_id").eq("user_id", userId).maybeSingle();
  return data != null;
}

export async function saveAnswer(viewer: SellIntentViewer, answer: SellIntentAnswer, source: SellIntentSource): Promise<void> {
  const { error } = await (await clientFor(viewer))
    .from("sell_intent")
    .upsert({ user_id: viewer.userId, ...answerRow(answer, source) }, { onConflict: "user_id" });
  if (error) throw new Error(`sell_intent: ${error.message}`);
}

/** Only after «Sí»: false when there is no «Sí» to add the notice to. */
export async function saveNotice(viewer: SellIntentViewer, agencies: boolean, config: SellIntentConfig): Promise<boolean> {
  const { data, error } = await (await clientFor(viewer))
    .from("sell_intent")
    .update(noticeRow(agencies, config))
    .eq("user_id", viewer.userId)
    .eq("answer", "yes")
    .select("user_id");
  if (error) throw new Error(`sell_intent: ${error.message}`);
  return (data ?? []).length > 0;
}
