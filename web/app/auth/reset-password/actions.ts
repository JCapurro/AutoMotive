"use server";

import { redirect } from "next/navigation";
import { safeNext } from "@/lib/navigation";
import { createClient } from "@/lib/supabase/server";

export type PasswordState = { error?: string };
export async function updatePassword(next: string, _prev: PasswordState, form: FormData): Promise<PasswordState> {
  const password = String(form.get("password") ?? "");
  if (password.length < 8) return { error: "Usá al menos 8 caracteres." };
  if (password !== form.get("confirmPassword")) return { error: "Las contraseñas no coinciden." };
  const supabase = await createClient();
  const { data, error: userError } = await supabase.auth.getUser();
  if (userError || !data.user) return { error: "El link venció. Pedí uno nuevo." };
  // An email-only account chooses its password after proving the inbox (/app/cuenta).
  const { data: profile } = await supabase.from("profiles").select("email_only").eq("id", data.user.id).maybeSingle();
  if (profile?.email_only) redirect(`/app/cuenta?${new URLSearchParams({ next: safeNext(next) })}`);
  const { error } = await supabase.auth.updateUser({ password });
  if (error) return { error: error.code === "same_password" ? "Elegí una contraseña distinta de la anterior." : "No pudimos actualizar la contraseña. Elegí una más segura o pedí un nuevo link." };
  const { error: signOutError } = await supabase.auth.signOut();
  if (signOutError) redirect("/app");
  redirect(`/login?${new URLSearchParams({ password: "updated", next: safeNext(next) })}`);
}
