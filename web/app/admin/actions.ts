"use server";

import { refresh } from "next/cache";
import { z } from "zod";

import { requireAdmin } from "@/lib/admin";
import { CommercialOfferInput } from "@/lib/commercial";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Json } from "@/types/database";

export type ActionResult = { ok?: boolean; error?: string };

const SourceInput = z.object({
  id: z.string().min(1),
  enabled: z.boolean(),
  crawl_interval_seconds: z.number().int().min(60, "Mínimo 1 minuto.").max(86_400, "Máximo un día."),
});

/** Fuentes: cadence and on/off (sección 5.1). The worker reads them every tick. */
export async function updateSource(input: z.input<typeof SourceInput>): Promise<ActionResult> {
  await requireAdmin();
  const parsed = SourceInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Datos inválidos." };
  const { id, ...values } = parsed.data;
  const { error } = await createAdminClient().from("sources").update(values).eq("id", id);
  if (error) return { error: error.message };
  refresh();
  return { ok: true };
}

function shape(value: unknown): string {
  return value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
}

/**
 * Config: one app_config value (Apéndice A), as JSON. Only existing keys and
 * the same shape as the current value: a typo must not create a setting nobody
 * reads. The worker picks it up within a minute (its config cache).
 */
export async function updateConfig(key: string, text: string): Promise<ActionResult> {
  await requireAdmin();
  if (key === "commercial_pilot") return { error: "Habilitá el piloto desde Cobros para iniciar las pruebas y aplicar límites juntos." };
  let value: Json;
  try {
    value = JSON.parse(text) as Json;
  } catch {
    return { error: "No es JSON válido." };
  }
  const admin = createAdminClient();
  const { data: current } = await admin.from("app_config").select("value").eq("key", key).maybeSingle();
  if (!current) return { error: `La clave ${key} no existe.` };
  if (value === null) return { error: "El valor no puede ser null." };
  if (key === "pro_offer" && !CommercialOfferInput.safeParse(value).success) return { error: "La oferta requiere una versión y los dos planes con importe entero positivo, moneda ARS y 30 días." };
  if (shape(current.value) !== shape(value)) {
    return { error: `El valor tiene que ser ${shape(current.value)}, como el actual.` };
  }
  const { error } = await admin.from("app_config").update({ value }).eq("key", key);
  if (error) return { error: error.message };
  refresh();
  return { ok: true };
}
