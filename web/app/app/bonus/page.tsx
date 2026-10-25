import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { requireUser } from "@/lib/auth";
import { bonusTrial } from "@/lib/bonus-trial";
import { accessDate } from "@/lib/pro";
import { createClient } from "@/lib/supabase/server";

import { startBonusTrial } from "./actions";

export const metadata: Metadata = { title: "7 días gratis" };

/**
 * The button of the bonus_trial_offer email (docs/MAILS_DE_PLAN.md, «Prueba
 * extra de 7 días»), reached through /m/<id>. Opening it changes nothing;
 * the button starts the 7 days and brings back the paused search.
 */
export default async function BonusTrialPage() {
  await requireUser();
  const supabase = await createClient();
  const { data } = await supabase.rpc("my_bonus_trial");
  const bonus = bonusTrial(data);

  return (
    <div className="mx-auto max-w-lg space-y-4">
      {bonus.state === "active" ? (
        <>
          <h1 className="text-xl font-semibold tracking-tight">Listo: tu búsqueda está activa</h1>
          <p className="text-muted-foreground">
            Tenés 7 días gratis{bonus.endsAt ? `, hasta el ${accessDate(bonus.endsAt)}` : ""}. Te avisamos por email
            cuando aparezca un auto que coincida. Al terminar se pausa sola.
          </p>
          <Button asChild className="h-10">
            <Link href="/app">Ver mis resultados</Link>
          </Button>
        </>
      ) : bonus.state === "available" ? (
        <>
          <h1 className="text-xl font-semibold tracking-tight">7 días gratis con tu búsqueda</h1>
          <p className="text-muted-foreground">
            Reactivamos tu búsqueda tal como estaba, con los avisos por email, durante 7 días. Sin tarjeta, y al
            terminar se pausa sola.
          </p>
          <form action={startBonusTrial}>
            <Button type="submit" className="h-10 w-full sm:w-auto">
              Activar mis 7 días
            </Button>
          </form>
        </>
      ) : (
        <>
          <h1 className="text-xl font-semibold tracking-tight">Esta prueba ya no está disponible</h1>
          <p className="text-muted-foreground">
            Los 7 días gratis son una sola vez por cuenta. Para seguir buscando, mirá los{" "}
            <Link href="/app/pro?plan=pass_30" className="underline">planes</Link>.
          </p>
        </>
      )}
    </div>
  );
}
