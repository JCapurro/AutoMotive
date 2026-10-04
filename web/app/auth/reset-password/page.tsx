import type { Metadata } from "next";
import Link from "next/link";
import { Logo } from "@/components/logo";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { createClient } from "@/lib/supabase/server";
import { PasswordForm } from "./password-form";

export const metadata: Metadata = { title: "Nueva contraseña" };
export default async function ResetPasswordPage() {
  const supabase = await createClient();
  const { data, error } = await supabase.auth.getUser();
  return <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
    <Logo /><Card className="w-full max-w-sm"><CardHeader><CardTitle>Nueva contraseña</CardTitle><CardDescription>Elegí una contraseña de al menos 8 caracteres.</CardDescription></CardHeader><CardContent>
      {data.user && !error ? <PasswordForm /> : <p role="alert" className="text-sm">El enlace venció o no es válido. <Link className="underline" href="/login?mode=recover">Pedí un nuevo email de recuperación</Link>.</p>}
    </CardContent></Card>
  </main>;
}
