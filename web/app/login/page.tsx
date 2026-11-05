import type { Metadata } from "next";
import { headers } from "next/headers";
import Link from "next/link";

import { Logo } from "@/components/logo";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { localMailbox } from "@/lib/env";
import { isInAppBrowser } from "@/lib/in-app-browser";
import { safeNext } from "@/lib/navigation";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Ingresar" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);
  const inApp = isInAppBrowser((await headers()).get("user-agent"));
  const paying = next.startsWith("/app/pro");
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
      <Logo />
      <Card className="w-full max-w-sm">
        <CardHeader>
          {/* Old links still carry ?mode=signup or ?mode=recover: there's one screen for all of them now. */}
          <CardTitle className="text-lg">Entrá a Ese Auto</CardTitle>
          <CardDescription>{paying ? "Para contratar un plan, entrá con tu email. Si es tu primera vez, te creamos la cuenta."
            : "Te mandamos un código a tu email para entrar. Sin contraseña."}</CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm next={next} linkError={params.error === "link"} googleError={params.error === "google"} mailbox={localMailbox} passwordUpdated={params.password === "updated"} inApp={inApp} />
        </CardContent>
      </Card>
      <p className="max-w-sm text-center text-xs text-muted-foreground">
        Al ingresar aceptás los{" "}
        <Link href="/terminos" className="underline">
          Términos de uso
        </Link>{" "}
        y la{" "}
        <Link href="/privacidad" className="underline">
          Política de privacidad
        </Link>
        .
      </p>
    </main>
  );
}
