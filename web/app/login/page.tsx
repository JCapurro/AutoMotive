import type { Metadata } from "next";
import Link from "next/link";

import { Logo } from "@/components/logo";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { localMailbox } from "@/lib/env";
import { safeNext } from "@/lib/navigation";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Ingresar" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);
  const mode = params.mode === "signup" || params.mode === "recover" ? params.mode : "login";
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
      <Logo />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-lg">{mode === "signup" ? "Creá tu cuenta" : mode === "recover" ? "Recuperá tu contraseña" : "Ingresá a tu cuenta"}</CardTitle>
          <CardDescription>Guardá tus búsquedas y recibí las alertas.</CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm key={mode} next={next} mode={mode} linkError={params.error === "link"} mailbox={localMailbox} passwordUpdated={params.password === "updated"} />
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
