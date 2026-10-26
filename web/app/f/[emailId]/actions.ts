"use server";

import { redirect } from "next/navigation";

import { feedbackEmail } from "@/lib/email-feedback";
import { feedbackComment, feedbackEmailId, feedbackReason } from "@/lib/email-feedback-reasons";
import { createAdminClient } from "@/lib/supabase/admin";

/** The confirm button of /f/<id>: the reason (and the comment, if any) for that email. */
export async function sendFeedback(formData: FormData): Promise<void> {
  const id = feedbackEmailId(formData.get("id"));
  const reason = feedbackReason(formData.get("r"));
  const signature = typeof formData.get("s") === "string" ? String(formData.get("s")) : null;
  if (id == null || !reason || !(await feedbackEmail(id, signature))) redirect("/f/0");
  const { error } = await createAdminClient().rpc("record_email_feedback", {
    p_email: id,
    p_reason: reason,
    p_comment: feedbackComment(formData.get("comment")),
  });
  if (error) throw new Error(error.message);
  redirect(`/f/${id}?listo=1`);
}
