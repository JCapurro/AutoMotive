import "server-only";

import { type DealerReach, parseReach } from "@/lib/dealer-funnel";
import { createClient } from "@/lib/supabase/server";

/**
 * my_dealer_reach() with the signed-in user's session: the RPC checks the
 * membership and rounds people to "few" in SQL. Null when it fails.
 */
export async function dealerReach(): Promise<DealerReach | null> {
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("my_dealer_reach");
  if (error) {
    console.error("my_dealer_reach:", error.code);
    return null;
  }
  return parseReach(data);
}
