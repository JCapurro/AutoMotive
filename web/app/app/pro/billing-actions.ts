"use server";
import { refresh } from "next/cache";
import { z } from "zod";
import { requireUser } from "@/lib/auth";
import { createCheckout, cancelSubscription, syncCheckout } from "@/lib/mercadopago-server";
import { createAdminClient } from "@/lib/supabase/admin";

export async function startPayment(offer: string, email: string, accepted: boolean, version: string, amount: number): Promise<{ url?: string; error?: string }> {
  const user = await requireUser();
  const input = z.object({ offer: z.enum(["pass_30", "pro_monthly"]), email: z.email().max(254), accepted: z.literal(true), version: z.string().min(1).max(80), amount: z.number().int().positive() }).safeParse({ offer, email, accepted, version, amount });
  if (!input.success) return { error: "Revisá el email y aceptá las condiciones del plan." };
  try { return { url: await createCheckout(user.id, input.data.offer, input.data.email, input.data.version, input.data.amount) }; }
  catch (error) {
    const message = error instanceof Error ? error.message : "";
    return { error: message === "offer_changed" ? "La oferta cambió. Actualizá la página y revisá el precio antes de pagar." : message === "paid_plan_already_active" ? "Ya tenés un plan pago vigente." : message === "checkout_already_open" || message === "checkout_in_progress" ? "Ya tenés una contratación en curso. Revisala abajo antes de iniciar otra." : "No pudimos iniciar el cobro. Revisá el estado de la contratación; si sigue pendiente, contactanos antes de volver a pagar." };
  }
}
async function ownedCheckout(id: string) {
  const user = await requireUser();
  if (!z.uuid().safeParse(id).success) throw new Error("unknown_checkout");
  const { data, error } = await createAdminClient().from("billing_checkouts").select("*").eq("id", id).eq("user_id", user.id).single();
  if (error || !data) throw new Error("unknown_checkout");
  return data;
}
export async function checkPayment(id: string): Promise<{ error?: string }> {
  const checkout = await ownedCheckout(id);
  // Avoid repeated provider queries by double clicking; webhooks and the cron remain authoritative.
  if (checkout.last_synced_at && Date.now() - new Date(checkout.last_synced_at).getTime() < 30000) { refresh(); return {}; }
  try { await syncCheckout(checkout); refresh(); return {}; }
  catch { return { error: "La verificación sigue pendiente. Tu acceso cambia únicamente al confirmar un pago aprobado." }; }
}
export async function stopSubscription(id: string): Promise<{ error?: string }> {
  const checkout = await ownedCheckout(id);
  try { await cancelSubscription(checkout); refresh(); return {}; }
  catch { return { error: "No pudimos confirmar la baja en Mercado Pago. La suscripción sigue pendiente de cancelación; intentá nuevamente o contactanos." }; }
}
