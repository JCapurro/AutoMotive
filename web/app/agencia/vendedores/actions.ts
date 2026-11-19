"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { requireUser } from "@/lib/auth";
import { sellerErrorText } from "@/lib/dealer-buying";
import { rpcCode } from "@/lib/dealer-program";
import { createClient } from "@/lib/supabase/server";

export type SellerRequestResult = { ok?: boolean; created?: boolean; error?: string };

const Input = z.object({ ref: z.string().regex(/^[0-9a-f]{32}$/), message: z.string().trim().max(300).optional() });

/**
 * An approved agency asks to contact a seller. Never returns a contact: the
 * seller decides (dealer_request_seller only records the request, with its caps).
 */
export async function requestSeller(ref: string, message?: string): Promise<SellerRequestResult> {
  await requireUser();
  const parsed = Input.safeParse({ ref, message });
  if (!parsed.success) return { error: sellerErrorText(message && message.length > 300 ? "invalid_message" : "seller_not_found") };
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("dealer_request_seller", {
    p_ref: parsed.data.ref,
    p_message: parsed.data.message || null,
  });
  if (error) {
    console.error("dealer_request_seller:", error.code);
    return { error: sellerErrorText(rpcCode(error.message)) };
  }
  revalidatePath("/agencia/vendedores");
  const created = !!data && typeof data === "object" && !Array.isArray(data) && (data as Record<string, unknown>).created === true;
  return { ok: true, created };
}
