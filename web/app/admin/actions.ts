"use server";

import { refresh } from "next/cache";

import { requireAdmin } from "@/lib/admin";
import { sameConfig, SourceUpdateInput, validateConfigChange } from "@/lib/admin-config";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Json } from "@/types/database";

export type ActionResult = { ok?: boolean; error?: string };

function writeError(message: string): string {
  if (message.includes("setting_conflict")) return "Otra persona cambió este valor. Recargá la página y revisá sus cambios antes de guardar.";
  if (message.includes("setting_not_found")) return "La configuración ya no existe. Recargá la página.";
  return "No pudimos confirmar el guardado y su historial. Recargá la página antes de reintentar.";
}

/** Worker picks up the exact cadence/state on its next configuration read. */
export async function updateSource(input: unknown): Promise<ActionResult> {
  const actor = await requireAdmin();
  const parsed = SourceUpdateInput.safeParse(input);
  if (!parsed.success) return { error: parsed.error.issues[0]?.message ?? "Datos inválidos." };
  const { id, expected, ...value } = parsed.data;
  const { error } = await createAdminClient().rpc("admin_update_setting", {
    p_target_type: "sources", p_target_key: id, p_expected: expected, p_value: value, p_actor_id: actor.id,
  });
  if (error) return { error: writeError(error.message) };
  refresh();
  return { ok: true };
}

/** Existing keys only. The RPC rechecks expected while holding the row lock. */
export async function updateConfig(key: string, text: string, expected: Json): Promise<ActionResult> {
  const actor = await requireAdmin();
  if (typeof key !== "string" || key.length < 1 || key.length > 200 || typeof text !== "string") return { error: "Datos inválidos." };
  if (key === "commercial_pilot") return { error: "Habilitá el piloto desde Cobros para iniciar las pruebas y aplicar límites juntos." };
  let value: Json;
  try {
    value = JSON.parse(text) as Json;
  } catch {
    return { error: "No es JSON válido." };
  }
  const admin = createAdminClient();
  const { data: current, error: readError } = await admin.from("app_config").select("value").eq("key", key).maybeSingle();
  if (readError) return { error: "No pudimos leer la configuración actual. Probá nuevamente." };
  if (!current) return { error: `La clave ${key} no existe.` };
  if (!sameConfig(current.value, expected)) return { error: writeError("setting_conflict") };
  const invalid = validateConfigChange(key, value, current.value);
  if (invalid) return { error: invalid };
  if (sameConfig(current.value, value)) return { ok: true };
  const { error } = await admin.rpc("admin_update_setting", {
    p_target_type: "app_config", p_target_key: key, p_expected: expected, p_value: value, p_actor_id: actor.id,
  });
  if (error) return { error: writeError(error.message) };
  refresh();
  return { ok: true };
}
