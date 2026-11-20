import { PhonePrompt } from "@/components/app/phone-form";
import { requireUser } from "@/lib/auth";
import type { PhonePromptPlace } from "@/lib/phone-prompt";
import { createClient } from "@/lib/supabase/server";

/**
 * The mobile asked again outside the results (Juan, 20/11): on the home, the
 * saved cars and a listing, for whoever still has none. Nothing once they left it.
 */
export async function PhoneAsk({ place, className }: { place: Exclude<PhonePromptPlace, "results">; className?: string }) {
  const user = await requireUser();
  const supabase = await createClient();
  const { data } = await supabase.from("profiles").select("phone").eq("id", user.id).maybeSingle();
  if (!data || data.phone) return null;
  return <div className={className}><PhonePrompt place={place} /></div>;
}
