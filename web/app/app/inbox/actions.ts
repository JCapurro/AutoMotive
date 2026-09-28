"use server";

import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

/** Web inbox: seeing an alert opens it (sección 7.3). Only opened_at can be written by the user (RLS). */
export async function markOpened(ids: number[]): Promise<void> {
  await requireUser();
  const valid = ids.filter((id) => Number.isInteger(id) && id > 0).slice(0, 200);
  if (!valid.length) return;
  const supabase = await createClient();
  await supabase.from("notifications").update({ opened_at: new Date().toISOString() }).in("id", valid).is("opened_at", null);
}
