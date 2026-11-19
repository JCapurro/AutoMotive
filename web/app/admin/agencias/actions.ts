"use server";

import { revalidatePath } from "next/cache";

import { requireAdmin } from "@/lib/admin";
import { createAdminClient } from "@/lib/supabase/admin";

export type AdminDealerResult = { ok?: boolean; error?: string };

function done(): AdminDealerResult {
  revalidatePath("/admin/agencias");
  return { ok: true };
}

const validId = (id: unknown): id is number => typeof id === "number" && Number.isInteger(id) && id > 0;

/** Approval turns on the demand counts and, with the channel on, sending to buyers (spec §0.7). */
export async function approveDealer(id: number): Promise<AdminDealerResult> {
  const actor = await requireAdmin();
  if (!validId(id)) return { error: "Agencia inválida." };
  const { error } = await createAdminClient().from("dealers")
    .update({ approved_at: new Date().toISOString(), approved_by: actor.id, status: "active" }).eq("id", id);
  if (error) return { error: "No pudimos aprobarla." };
  return done();
}

/** Paused: its cars stop reaching buyers on the worker's next sweep (≤ 120 s); resumed: back to active. */
export async function pauseDealer(id: number, paused: boolean): Promise<AdminDealerResult> {
  await requireAdmin();
  if (!validId(id) || typeof paused !== "boolean") return { error: "Agencia inválida." };
  const { error } = await createAdminClient().from("dealers").update({ status: paused ? "paused" : "active" }).eq("id", id);
  if (error) return { error: "No pudimos cambiarla." };
  return done();
}

/** The seller account of that source is the agency's: the worker links its active listings on its next tick. */
export async function approveSource(id: number, sellerKey: string): Promise<AdminDealerResult> {
  await requireAdmin();
  const key = typeof sellerKey === "string" ? sellerKey.trim() : "";
  if (!validId(id) || !key || key.length > 300) return { error: "Elegí la cuenta del vendedor." };
  const { error } = await createAdminClient().from("dealer_sources")
    .update({ status: "approved", seller_key: key, approved_at: new Date().toISOString() }).eq("id", id);
  if (error) return { error: error.code === "23505" ? "Esa cuenta ya es de otra agencia." : "No pudimos aprobarla." };
  return done();
}

export async function rejectSource(id: number): Promise<AdminDealerResult> {
  await requireAdmin();
  if (!validId(id)) return { error: "Fuente inválida." };
  const { error } = await createAdminClient().from("dealer_sources").update({ status: "rejected", approved_at: null }).eq("id", id);
  if (error) return { error: "No pudimos rechazarla." };
  return done();
}
