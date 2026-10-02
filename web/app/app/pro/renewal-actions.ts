"use server";
import { refresh } from "next/cache";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

export async function declineRenewal(): Promise<{ error?: string }> {
  await requireUser();
  const db = await createClient();
  const { error } = await db.rpc("decline_commercial_renewal");
  if (error) return { error: "No pudimos registrar el aviso. Revisá tu acceso o probá nuevamente." };
  refresh();
  return {};
}
