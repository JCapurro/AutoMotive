import Link from "next/link";

import { DealerSignupForm } from "@/components/agencia/dealer-signup-form";
import { PendingSales } from "@/components/agencia/sale-question";
import { Button } from "@/components/ui/button";
import { webConfig } from "@/lib/config";
import { reachSentence, salesSentence } from "@/lib/dealer-funnel";
import { dealerReach } from "@/lib/dealer-funnel-server";
import { channelOn } from "@/lib/dealer-program";
import { myDealer } from "@/lib/dealer-server";
import { number } from "@/lib/format";

/** Without an agency: the sign-up. With one: the summary and what needs doing. */
export default async function DealerHome() {
  const [dealer, { dealerProgram }] = await Promise.all([myDealer(), webConfig()]);
  if (!dealer) return <DealerSignupForm />;
  const { counts } = dealer;
  const channel = channelOn(dealerProgram);
  // The value of the channel: this month's reach (people rounded to «pocas» in SQL) and the sales to answer.
  const reach = channel && dealer.approved ? await dealerReach() : null;
  const sales = reach ? salesSentence(reach.sales_via_ese_auto) : null;

  return (
    <div className="space-y-6">
      <h1 className="type-heading text-[1.9rem] leading-tight">{dealer.name}</h1>

      {reach ? (
        <p data-testid="dealer-reach" className="border-l-4 border-foreground pl-4 text-[17px] leading-snug">
          <b className="font-semibold">{reachSentence(reach)}</b>
          {sales ? <span className="block text-[15px] text-muted-foreground">{sales}</span> : null}
        </p>
      ) : null}
      {reach ? <PendingSales sales={reach.pending_sales} /> : null}

      {!dealer.approved ? (
        <p role="status" data-testid="dealer-not-approved" className="rounded-lg bg-muted p-4 text-[15px]">
          <b className="font-semibold">Tu agencia se activa con el plan Pro.</b> Mientras tanto ves tus precios contra el mercado. Con Pro activo ves
          cuánta gente busca cada auto y tus autos les llegan a los compradores. <Link href="/planes" className="font-semibold underline underline-offset-2">Ver planes</Link>
        </p>
      ) : null}
      {counts.unconfirmed > 0 ? (
        <p role="status" data-testid="dealer-unconfirmed" className="rounded-lg bg-warn-soft p-4 text-[15px]">
          <b className="font-semibold">Confirmá tu stock.</b> Hay {number(counts.unconfirmed)} {counts.unconfirmed === 1 ? "auto" : "autos"} sin confirmar hace más de{" "}
          {dealerProgram.manualConfirmDays} días: no se {counts.unconfirmed === 1 ? "envía" : "envían"} a compradores hasta que lo confirmes.{" "}
          <Link href="/agencia/stock" className="font-semibold underline underline-offset-2">Ir al stock</Link>
        </p>
      ) : null}
      {counts.review > 0 ? (
        <p role="status" className="rounded-lg bg-muted p-4 text-[15px]">
          {counts.review === 1
            ? "Un auto parece estar ya publicado por vos en otro sitio."
            : `${number(counts.review)} autos parecen estar ya publicados por vos en otro sitio.`}{" "}
          <Link href="/agencia/stock" className="font-semibold underline underline-offset-2">{counts.review === 1 ? "Revisalo" : "Revisalos"}</Link>
        </p>
      ) : null}

      <dl className="grid grid-cols-2 gap-x-6 border-t-2 border-foreground sm:grid-cols-4">
        <Stat label="Disponibles">{counts.available}</Stat>
        <Stat label="Reservados">{counts.reserved}</Stat>
        <Stat label="Vendidos">{counts.sold}</Stat>
        <Stat label="Consultas nuevas">{channel ? counts.leads_new : "—"}</Stat>
      </dl>

      <div className="flex flex-wrap gap-2">
        <Button asChild className="h-10"><Link href="/agencia/stock">Ver mi stock</Link></Button>
        <Button asChild variant="outline" className="h-10"><Link href="/agencia/stock/planilla">Subir planilla</Link></Button>
        <Button asChild variant="outline" className="h-10"><Link href="/agencia/stock/nuevo">Cargar un auto</Link></Button>
      </div>
      {!channel ? <p className="text-sm text-muted-foreground">El canal de venta todavía no está activo: tus autos no se envían a compradores.</p> : null}
    </div>
  );
}

function Stat({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-b py-3">
      <dt className="text-[13px] text-muted-foreground">{label}</dt>
      <dd className="type-figure mt-0.5 text-2xl">{typeof children === "number" ? number(children) : children}</dd>
    </div>
  );
}
