import type { Metadata } from "next";

import { Logo } from "@/components/logo";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNext } from "@/lib/navigation";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Ingresar" };

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const params = await searchParams;
  const next = safeNext(typeof params.next === "string" ? params.next : null);
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
      <Logo />
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-lg">Ingresá o creá tu cuenta</CardTitle>
          <CardDescription>Guardá tus búsquedas y recibí las alertas.</CardDescription>
        </CardHeader>
        <CardContent>
          <LoginForm next={next} linkError={params.error === "link"} />
        </CardContent>
      </Card>
    </main>
  );
}
