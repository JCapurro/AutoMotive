import { ArrowRight, Loader2, Plus, Send } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ListingCard } from "@/components/app/listing-card";
import { ProBanner } from "@/components/app/pro-cta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { requireUser } from "@/lib/auth";
import type { ProCtaState } from "@/lib/pro";
import { describeFilters, describeVehicle } from "@/lib/search";
import { createClient } from "@/lib/supabase/server";
import type { Filters } from "@/lib/types";

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
  // §52: "Probar Automotive Pro" after real activity or a plan limit.
  const pro = (cta ?? null) as ProCtaState | null;
  const { data: radii } = await supabase.from("search_profiles").select("id, radius_km");
  const radius = new Map((radii ?? []).map((r) => [r.id, r.radius_km]));

  if (!searches?.length) {
    return (
      <div className="mx-auto max-w-lg space-y-6 py-10 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Creá tu primera búsqueda</h1>
        <p className="text-muted-foreground">
          Decinos qué auto estás buscando. Automotive monitorea las publicaciones y te avisa cuando aparece uno que
          coincide.
        </p>
        <Button asChild size="lg" className="h-11 px-5 text-base">
          <Link href="/app/searches/new">
            <Plus aria-hidden /> Crear mi búsqueda
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h1 className="text-xl font-semibold tracking-tight">Mis búsquedas</h1>
          <Button asChild size="sm" variant="outline" className="md:hidden">
            <Link href="/app/searches/new">
              <Plus aria-hidden /> Nueva
            </Link>
          </Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          {searches.map((s) => {
            const filters = s.filters as Filters;
            return (
              <Card key={s.profile_id} size="sm" className={s.enabled ? undefined : "opacity-70"} data-testid="search-card">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Link href={`/app/searches/${s.profile_id}`} className="truncate hover:underline">
                      {s.name}
                    </Link>
                    {!s.enabled ? <Badge variant="secondary">Pausada</Badge> : null}
                  </CardTitle>
                  <CardDescription className="truncate">
                    {describeVehicle(filters)} · {describeFilters(filters, radius.get(s.profile_id))}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex items-end justify-between gap-3">
                  {s.pending ? (
                    <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Loader2 className="size-4 animate-spin" aria-hidden /> Buscando publicaciones…
                    </p>
                  ) : (
                    <p className="text-sm">
                      <span className="font-semibold tabular-nums">{s.new_this_week}</span> nuevos esta semana ·{" "}
                      <span className="font-semibold tabular-nums">{s.opportunities_this_week}</span>{" "}
                      {s.opportunities_this_week === 1 ? "oportunidad" : "oportunidades"}
                    </p>
                  )}
                  <Button asChild size="sm" variant="ghost" className="shrink-0">
                    <Link href={`/app/searches/${s.profile_id}`}>
                      Ver resultados <ArrowRight aria-hidden />
                    </Link>
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {pro?.show && pro.reason ? <ProBanner placement="dashboard" reason={pro.reason} /> : null}

      {!profile?.telegram_chat_id ? (
        <Link
          href="/app/settings#telegram"
          className="flex items-center gap-3 rounded-xl bg-sky-50 p-4 text-sm text-sky-950 ring-1 ring-sky-200 hover:bg-sky-100"
        >
          <Send className="size-5 shrink-0" aria-hidden />
          <span>
            <span className="font-medium">Recibí las alertas en Telegram.</span> Vinculá tu cuenta en un paso.
          </span>
          <ArrowRight className="ml-auto size-4 shrink-0" aria-hidden />
        </Link>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Oportunidades recientes</h2>
        {opportunities?.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {opportunities.map((card) => (
              <ListingCard key={card.listing_id} card={card} showProfile />
            ))}
          </div>
        ) : (
          <p className="rounded-xl bg-card p-6 text-center text-sm text-muted-foreground ring-1 ring-foreground/10">
            Todavía no hay oportunidades 🔥 ni buenas coincidencias 🟢 de los últimos 14 días. Te avisamos cuando
            aparezcan.
          </p>
        )}
      </section>
    </div>
  );
}
