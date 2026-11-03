import "server-only";

import { createClient } from "@supabase/supabase-js";

import { supabaseAnonKey, supabaseUrl } from "@/lib/env";
import type { Database } from "@/types/database";

/**
 * PAR-04: the anonymous client of the public pages (/guias). No cookies and
 * no session, so the page stays static (ISR) and RLS is what guarantees that
 * only published guides are read.
 */
export function createPublicClient() {
  return createClient<Database>(supabaseUrl, supabaseAnonKey, {
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
}
