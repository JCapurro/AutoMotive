import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { safeNext } from "@/lib/navigation";

export const metadata: Metadata = { title: "Confirmá tu email", robots: { index: false, follow: false }, referrer: "strict-origin" };

export default async function ConfirmEmailPage({ searchParams }: PageProps<"/auth/confirm-email">) {
  const params = await searchParams;
  const tokenHash = typeof params.token_hash === "string" ? params.token_hash : "";
  const type = typeof params.type === "string" ? params.type : "";
  const recovery = type === "recovery";
  const next = recovery ? "/auth/reset-password" : safeNext(typeof params.next === "string" ? params.next : null);
  if (!tokenHash || !["signup", "email", "recovery", "email_change", "invite", "magiclink"].includes(type)) redirect("/login?error=link");
  return <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-10">
    <Logo />
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>{recovery ? "Recuperá tu contraseña" : "Confirmá tu email"}</CardTitle>
        <CardDescription>{recovery ? "Continuá para elegir una nueva contraseña." : "Confirmá tu email para completar el registro e ingresar a tu cuenta."}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form action="/auth/confirm" method="post">
          <input type="hidden" name="token_hash" value={tokenHash} />
          <input type="hidden" name="type" value={type} />
          <input type="hidden" name="next" value={next} />
          <Button className="h-10 w-full" type="submit">{recovery ? "Elegir nueva contraseña" : "Confirmar mi email"}</Button>
        </form>
        <p className="text-center text-sm"><Link href="/login" className="underline">Ya confirmé mi cuenta. Ingresar</Link></p>
      </CardContent>
    </Card>
  </main>;
}
