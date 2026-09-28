"use server";

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";
import { unsubscribeToken } from "@/lib/unsubscribe";

/** The confirm button of /baja: takes email out of every search, no login needed. */
export async function unsubscribe(formData: FormData): Promise<void> {
  const token = unsubscribeToken(formData.get("t"));
  if (!token) redirect("/baja");
  const supabase = await createClient();
  const { data, error } = await supabase.rpc("unsubscribe_email", { p_token: token });
  if (error) throw new Error(error.message);
  redirect(data ? "/baja?listo=1" : "/baja");
}
