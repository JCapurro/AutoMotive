import "server-only";

import type { SupabaseClient } from "@supabase/supabase-js";

import type { Database, Json } from "@/types/database";

/**
 * Tracking events (sección 11), written with the user's own client: RLS only
 * lets a user log events as themselves. A failed event never breaks the action.
 */
export async function track(
  supabase: SupabaseClient<Database>,
  userId: string,
  name: string,
  props: Record<string, Json | undefined> = {},
): Promise<void> {
  const { error } = await supabase.from("events").insert({ user_id: userId, name, props: props as { [key: string]: Json } });
  if (error) console.error(`event ${name} not recorded:`, error.message);
}
