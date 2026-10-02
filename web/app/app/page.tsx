import { Loader2, Pause, Plus, Send } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { LISTING_ROWS, ListingCard } from "@/components/app/listing-card";
import { ProBanner } from "@/components/app/pro-cta";
import { Button } from "@/components/ui/button";
import { requireUser } from "@/lib/auth";
import type { ProCtaState } from "@/lib/pro";
import { describeVehicle, filterParts } from "@/lib/search";
import { createClient } from "@/lib/supabase/server";
import type { Filters } from "@/lib/types";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Inicio" };

// §28: "Mis búsquedas" cards and "Oportunidades recientes" by score, then detection date.
export default async function Dashboard() {
  await requireUser();
  const supabase = await createClient();
  const [{ data: searches }, { data: opportunities }, { data: profile }, { data: cta }] = await Promise.all([
    supabase.rpc("dashboard_summary"),
    supabase.rpc("recent_opportunities", { p_limit: 8 }),
    supabase.from("profiles").select("telegram_chat_id").maybeSingle(),
    supabase.rpc("pro_cta_state"),
  ]);
  // §52: "Ver planes" after real activity or a plan limit.
  const pro = (cta ?? null) as ProCtaState | null;
  const { data: radii } = await supabase.from("search_profiles").select("id, radius_km");
  const radius = new Map((radii ?? []).map((r) => [r.id, r.radius_km]));

  if (!searches?.length) {
    return (
      <div className="mx-auto max-w-lg space-y-6 py-10 text-center">
        <h1 className="type-heading text-3xl">Creá tu primera búsqueda</h1>
        <p className="text-muted-foreground">
          Decinos qué auto estás buscando. Ese Auto monitorea las publicaciones y te avisa cuando aparece uno que
          coincide.
        </p>
        <Button asChild className="h-11 px-4.5 text-[15px]">
          <Link href="/app/searches/new">
            <Plus aria-hidden /> Crear mi búsqueda
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-12">
      <section>
        <div className="flex items-end justify-between gap-3">
          <h1 className="type-heading text-[30px] leading-tight">Mis búsquedas</h1>
          <Button asChild variant="outline" className="h-9 md:hidden">
            <Link href="/app/searches/new">
              <Plus aria-hidden /> Nueva
            </Link>
          </Button>
        </div>
        <div className="mt-5 border-t-2 border-foreground">
          <div aria-hidden className="hidden grid-cols-[minmax(0,1fr)_130px_130px_150px] border-b py-2.5 text-[13px] text-muted-foreground md:grid">
            <span>Búsqueda</span>
            <span className="text-right">Nuevos esta semana</span>
            <span className="text-right">Oportunidades</span>
            <span />
          </div>
          {searches.map((s) => {
            const filters = s.filters as Filters;
            return (
              <div
                key={s.profile_id}
                data-testid="search-card"
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2.5 border-b py-4 md:grid-cols-[minmax(0,1fr)_130px_130px_150px]"
              >
                <div className="min-w-0">
                  <Link
                    href={`/app/searches/${s.profile_id}`}
                    className={cn("text-lg font-bold underline-offset-4 hover:underline", !s.enabled && "text-faint")}
                  >
                    {s.name}
                  </Link>
                  {!s.enabled ? (
                    <span className="ml-2 inline-flex h-5.5 items-center gap-1 rounded-full bg-muted px-2 align-[3px] text-xs font-semibold text-muted-foreground">
                      <Pause className="size-3" aria-hidden /> Pausada
                    </span>
                  ) : null}
                  <ul aria-label="Filtros" className="mt-1.5 flex flex-wrap gap-1.5">
                    {[describeVehicle(filters), ...filterParts(filters, radius.get(s.profile_id))].filter(Boolean).map((part) => (
                      <li key={part} className="rounded bg-muted px-2 py-0.5 text-[13px] text-muted-foreground [font-stretch:92%]">
                        {part}
                      </li>
                    ))}
                  </ul>
                </div>
                {s.pending ? (
                  <p className="col-span-full flex items-center gap-2 text-sm text-muted-foreground md:col-span-2 md:col-start-2 md:row-start-1 md:justify-end">
                    <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden /> Buscando publicaciones…
                  </p>
                ) : (
                  <p
                    className={cn(
                      "col-span-full flex gap-5 md:col-span-2 md:col-start-2 md:row-start-1 md:grid md:grid-cols-2 md:gap-0",
                      !s.enabled && "text-faint",
                    )}
                  >
                    <span className="md:text-right">
                      <b className="type-figure text-xl">{s.new_this_week}</b>
                      <span className="ml-1 text-[13px] text-muted-foreground md:sr-only"> nuevos esta semana</span>
                    </span>
                    <span className="md:text-right">
                      <b className={cn("type-figure text-xl", s.opportunities_this_week ? "mark" : undefined)}>
                        {s.opportunities_this_week}
                      </b>
                      <span className="ml-1 text-[13px] text-muted-foreground md:sr-only">
                        {" "}
                        {s.opportunities_this_week === 1 ? "oportunidad" : "oportunidades"}
                      </span>
                    </span>
                  </p>
                )}
                <Button asChild variant="outline" className="col-start-2 row-start-1 h-9 self-start md:col-start-4 md:self-center md:justify-self-end">
                  <Link href={`/app/searches/${s.profile_id}`}>Ver resultados</Link>
                </Button>
              </div>
            );
          })}
        </div>

        {!profile?.telegram_chat_id ? (
          <Link
            href="/app/settings#telegram"
            className="group mt-5 flex items-center gap-3.5 rounded-lg bg-muted px-4 py-3.5 text-[15px]"
          >
            <Send className="size-5 shrink-0" aria-hidden />
            <span>
              <b className="font-bold">Recibí las alertas en Telegram.</b>{" "}
              <span className="text-muted-foreground">Vinculá tu cuenta en un paso.</span>
            </span>
            <span className="ml-auto shrink-0 font-semibold underline-offset-4 group-hover:underline">Vincular</span>
          </Link>
        ) : null}
      </section>

      {pro?.show && pro.reason ? <ProBanner placement="dashboard" reason={pro.reason} /> : null}

      <section>
        <h2 className="type-heading text-[22px] leading-tight">Oportunidades recientes</h2>
        <p className="mt-1 text-sm text-muted-foreground">Las de los últimos 14 días, ordenadas por Opportunity Score.</p>
        {opportunities?.length ? (
          <div className={cn(LISTING_ROWS, "mt-4")}>
            {opportunities.map((card) => (
              <ListingCard key={card.listing_id} card={card} showProfile />
            ))}
          </div>
        ) : (
          <p className="mt-4 rounded-lg bg-muted p-6 text-center text-sm text-muted-foreground">
            Todavía no hay oportunidades ni buenas coincidencias de los últimos 14 días. Te avisamos cuando aparezcan.
          </p>
        )}
      </section>
    </div>
  );
}
