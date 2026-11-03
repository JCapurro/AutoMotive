"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { webConfig } from "@/lib/config";
import { fichaReturnPath, sellIntentAnswer, sellIntentEmailId } from "@/lib/sell-intent";
import { resolveViewer, saveAnswer, saveNotice } from "@/lib/sell-intent-server";

function text(formData: FormData, name: string): string | null {
  const value = formData.get(name);
  return typeof value === "string" && value ? value : null;
}

/** /vender-mi-auto with the email link's id and signature (never the answer: that's saved now). */
function pagePath(id: number | null, signature: string | null, extra: Record<string, string> = {}): string {
  const query = new URLSearchParams();
  if (id != null) query.set("e", String(id));
  if (id != null && signature) query.set("s", signature);
  for (const [key, value] of Object.entries(extra)) query.set(key, value);
  const qs = query.toString();
  return `/vender-mi-auto${qs ? `?${qs}` : ""}`;
}

/**
 * The answer, from the confirm form of /vender-mi-auto (the email's links) or
 * from the listing page's line (a session). «No» from the listing page goes
 * back to it, where the line no longer shows.
 */
export async function answerSellIntent(formData: FormData): Promise<void> {
  const id = sellIntentEmailId(formData.get("e"));
  const signature = text(formData, "s");
  const answer = sellIntentAnswer(formData.get("r"));
  const viewer = await resolveViewer(id, signature);
  if (!viewer || !answer) redirect(pagePath(id, signature));
  await saveAnswer(viewer, answer, viewer.link ? "email" : "ficha");
  const back = fichaReturnPath(formData.get("volver"));
  if (back) revalidatePath(back);
  if (answer === "no" && back && !viewer.link) redirect(back);
  redirect(pagePath(id, signature));
}

/** «Avisame cuando esté», with the agencies box only while its flag is on. */
export async function requestSellNotice(formData: FormData): Promise<void> {
  const id = sellIntentEmailId(formData.get("e"));
  const signature = text(formData, "s");
  const viewer = await resolveViewer(id, signature);
  if (!viewer) redirect(pagePath(id, signature));
  const config = (await webConfig()).sellIntent;
  await saveNotice(viewer, formData.get("agencias") === "on", config);
  redirect(pagePath(id, signature));
}
