import "server-only";

import { createClient } from "@supabase/supabase-js";

import { supabaseUrl } from "@/lib/env";
import type { Database } from "@/types/database";

/**
 * Service role: bypasses RLS. Only for what no user may do on their own —
 * /r/<id> click tracking (track_notification_click) and reading app_config.
 */
export function createAdminClient() {
  return createClient<Database>(supabaseUrl, process.env.SUPABASE_SERVICE_ROLE_KEY!, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
