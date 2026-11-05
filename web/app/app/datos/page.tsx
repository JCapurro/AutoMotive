import type { Metadata } from "next";
import Link from "next/link";

import { PhoneForm } from "@/components/app/phone-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { requireUser } from "@/lib/auth";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Mis datos" };

/**
 * «Mis datos», from the account menu: the email (fixed, it's the account),
 * the mobile, the password and signing out. Alerts and plan stay in Ajustes.
 */
export default async function MyDataPage() {
  const user = await requireUser();
  const supabase = await createClient();
  const { data: profile } = await supabase.from("profiles").select("email, phone, email_only").eq("id", user.id).maybeSingle();
  const email = profile?.email ?? user.email ?? "";
  const emailOnly = profile?.email_only === true;
  const back = encodeURIComponent("/app/datos");

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-xl font-semibold tracking-tight">Mis datos</h1>

      <Card>
        <CardHeader>
          <CardTitle>Contacto</CardTitle>
          <CardDescription>Te avisamos por email. El celular es opcional: no se lo damos a vendedores ni a nadie.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1">
            <p className="text-sm font-medium">Email</p>
            <p className="text-sm [overflow-wrap:anywhere]">{email}</p>
            <p className="text-xs text-muted-foreground">Es el de tu cuenta y no se puede cambiar. ¿Está mal? Borrá la cuenta desde Ajustes y creá la búsqueda de nuevo con el correcto.</p>
          </div>
          <PhoneForm phone={profile?.phone ?? null} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Contraseña</CardTitle>
          <CardDescription>
            {emailOnly
              ? "Todavía no tenés. Entrás con un código que te llega al email; la contraseña hace falta para contratar un plan."
              : "Podés entrar con tu contraseña o con un código por email."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline">
            <Link href={emailOnly ? `/app/cuenta?next=${back}` : `/auth/reset-password?next=${back}`}>{emailOnly ? "Elegir contraseña" : "Cambiar contraseña"}</Link>
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sesión</CardTitle>
          <CardDescription>Para volver a entrar, pedí un código con tu email.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action="/auth/signout" method="post">
            <Button type="submit" variant="outline">Cerrar sesión</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
