"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

import { requireUser } from "@/lib/auth";
import { saleErrorText } from "@/lib/dealer-funnel";
import { createClient } from "@/lib/supabase/server";

const SaleInput = z
  .object({
    itemId: z.number().int().positive().nullable().optional(),
    leadId: z.number().int().positive().nullable().optional(),
    viaEseAuto: z.boolean(),
  })
  .refine((v) => v.itemId != null || v.leadId != null);

/** «¿La venta vino por Ese Auto?»: the agency's answer for a car marked sold or a lead marked «Compró». */
export async function declareSale(input: { itemId?: number | null; leadId?: number | null; viaEseAuto: boolean }): Promise<{ ok?: boolean; error?: string }> {
  await requireUser();
  const parsed = SaleInput.safeParse(input);
  if (!parsed.success) return { error: saleErrorText("invalid_sale") };
  const supabase = await createClient();
  const { error } = await supabase.rpc("dealer_declare_sale", {
    p_item_id: parsed.data.itemId ?? null,
    p_lead_id: parsed.data.leadId ?? null,
    p_via_ese_auto: parsed.data.viaEseAuto,
  });
  if (error) {
    console.error("agencia dealer_declare_sale:", String(error.message ?? "").slice(0, 80));
    return { error: saleErrorText(error.message) };
  }
  revalidatePath("/agencia", "layout");
  return { ok: true };
}
