import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/logo";
import { redirect } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNext } from "@/lib/navigation";
import { createClient } from "@/lib/supabase/server";
import { PasswordForm } from "./password-form";

export const metadata: Metadata = { title: "Nueva contraseña" };
export default async function ResetPasswordPage({ searchParams }: PageProps<"/auth/reset-password">) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getUser();
  if (data.user && !error) {
    // An email-only account chooses its password after proving the inbox.
    const { data: profile } = await supabase.from("profiles").select("email_only").eq("id", data.user.id).maybeSingle();
    if (profile?.email_only) redirect(`/app/cuenta?${new URLSearchParams({ next })}`);
  }
  return <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
    <Logo /><Card className="w-full max-w-sm"><CardHeader><CardTitle>Nueva contraseña</CardTitle><CardDescription>Elegí una contraseña de al menos 8 caracteres.</CardDescription></CardHeader><CardContent>
      {data.user && !error ? <PasswordForm next={next} /> : <p role="alert" className="text-sm">Este link ya se usó o venció. <Link className="underline" href={`/login?${new URLSearchParams({ mode: "recover", next })}`}>Pedí uno nuevo</Link>.</p>}
    </CardContent></Card>
  </main>;
}
