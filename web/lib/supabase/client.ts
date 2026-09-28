import { createBrowserClient } from "@supabase/ssr";

import { supabaseAnonKey, supabaseUrl } from "@/lib/env";
import type { Database } from "@/types/database";

/** Browser client (Realtime, clipboard-side reads). One per tab. */
export function createClient() {
  return createBrowserClient<Database>(supabaseUrl, supabaseAnonKey);
}
