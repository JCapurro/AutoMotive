"use server";

import { refresh } from "next/cache";
import { requireAdmin } from "@/lib/admin";
import { PaymentInput, commercialError } from "@/lib/commercial";
import { createClient } from "@/lib/supabase/server";

export async function confirmPayment(raw: unknown): Promise<{ error?: string; id?: number }> {
  await requireAdmin();
  const parsed = PaymentInput.safeParse(raw);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Revisá los datos." };
  const p = parsed.data;
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("record_commercial_payment", {
    p_user: p.userId, p_offer: p.offer, p_provider: p.provider, p_reference: p.reference,
    p_paid_at: p.paidAt, p_note: p.note,
  });
  if (error) return { error: commercialError(error.message) };
  refresh();
  return { id: data ?? undefined };
}
export async function recordRefund(id: number, reference: string): Promise<{ error?: string }> {
  await requireAdmin();
  if (!Number.isSafeInteger(id) || id <= 0 || typeof reference !== "string" || reference.trim().length < 3 || reference.length > 160)
    return { error: "Ingresá la referencia de la devolución ya realizada." };
  const supabase = await createClient();
  const { error } = await supabase.rpc("refund_commercial_payment", { p_id: id, p_reference: reference.trim() });
  if (error) return { error: commercialError(error.message) };
  refresh();
  return {};
}
export async function launchCommercialPilot(): Promise<{ error?: string }> {
  await requireAdmin();
  const supabase = await createClient();
  const { error } = await supabase.rpc("enable_commercial_pilot");
  if (error) return { error: commercialError(error.message) };
  refresh();
  return {};
}
