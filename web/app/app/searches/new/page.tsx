import { Sparkles } from "lucide-react";
import type { Metadata } from "next";
import { headers } from "next/headers";

import { AssistedSearch } from "@/components/app/assisted-search";
import { SearchForm } from "@/components/app/search-form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { SearchLimit } from "@/lib/assisted";
import { isEmailOnly, requireUser } from "@/lib/auth";
import { webConfig } from "@/lib/config";
import { track } from "@/lib/events";
import { type PlanLimits, planPrice, searchCapacity } from "@/lib/pro";
import type { SearchValues } from "@/lib/search-form";
import { searchIntentPrompt } from "@/lib/search-intent";
import { approximateLocationFromHeaders } from "@/lib/search-location";
import { createClient } from "@/lib/supabase/server";

import { loadFormData } from "../form-data";

export const metadata: Metadata = { title: "Nueva búsqueda" };

export default async function NewSearchPage({ searchParams }: PageProps<"/app/searches/new">) {
  const user = await requireUser();
  const approximateLocation = approximateLocationFromHeaders(await headers());
  const prompt = searchIntentPrompt((await searchParams).prompt);
  const supabase = await createClient();
  const [{ catalog, sources, defaultFrequency, thresholdAlerts, modelLessSearch }, { data: snapshot }, cfg, emailOnly] = await Promise.all([
    loadFormData(supabase),
    supabase.rpc("my_plan_snapshot"),
    webConfig(),
    isEmailOnly(),
  ]);
  // An email-only account comes from the landing with what it wants: here without it, the intent got lost on the way.
  if (emailOnly && !prompt) await recordMissingIntent(supabase, user.id);
  // One model is one search: a request with more models than the plan has room for asks which to activate.
  const access = (snapshot ?? null) as PlanLimits | null;
  const capacity = searchCapacity(access);
  const limit: SearchLimit | null = access && capacity != null ? {
    capacity,
    maxProfiles: access.limits.max_profiles ?? capacity,
    activeSearches: access.active_searches ?? 0,
    upsell: access.plan === "free"
      ? `Con Particular seguís hasta ${cfg.planLimits.pass.maxProfiles} modelos a la vez por ${planPrice(cfg.proOffer.pass_30.amount)}.`
      : null,
  } : null;

  const initial: SearchValues = {
    name: "",
    make: "",
    model: "",
    trim: "",
    trims: [],
    trim_strict: false,
    year_min: null,
    year_max: null,
    price_max: null,
    currency: "USD",
    km_max: null,
    transmission: "",
    fuel: "",
    body_types: [],
    sources: sources.map((s) => s.id),
    location: null,
    km_target: null,
    price_target: null,
    seller_type: "",
    notification_frequency: defaultFrequency,
    notify_min_level: "good",
    opportunity_threshold_pct: null,
  };

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Nueva búsqueda</h1>
        <p className="text-sm text-muted-foreground">Decinos qué auto estás buscando. Ese Auto monitorea por vos.</p>
      </div>
      {emailOnly && user.email ? <p className="rounded-lg bg-muted px-4 py-3 text-sm [overflow-wrap:anywhere]">
        Te vamos a avisar a <b>{user.email}</b>. Si no ves nuestros emails, buscalos en Spam o Promociones.
      </p> : null}
      <Tabs defaultValue="assisted">
        <TabsList>
          <TabsTrigger value="assisted">
            <Sparkles aria-hidden /> Asistido
          </TabsTrigger>
          <TabsTrigger value="structured">Estructurado</TabsTrigger>
        </TabsList>
        <TabsContent value="structured" className="pt-3">
          <SearchForm
            catalog={catalog}
            sources={sources}
            initial={initial}
            profileId={null}
            approximateLocation={approximateLocation}
            thresholdAlerts={thresholdAlerts}
            modelLessSearch={modelLessSearch}
          />
        </TabsContent>
        <TabsContent value="assisted" forceMount className="pt-3 data-[state=inactive]:hidden">
          <AssistedSearch
            catalog={catalog}
            sources={sources}
            base={initial}
            initialText={prompt}
            approximateLocation={approximateLocation}
            limit={limit}
            thresholdAlerts={thresholdAlerts}
            modelLessSearch={modelLessSearch}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/** search_intent_missing, once per account: an email-only sign-up without searches landed here without its prompt. */
async function recordMissingIntent(supabase: Awaited<ReturnType<typeof createClient>>, userId: string) {
  const [{ count: searches }, { count: recorded }] = await Promise.all([
    supabase.from("search_profiles").select("id", { count: "exact", head: true }),
    supabase.from("events").select("id", { count: "exact", head: true }).eq("name", "search_intent_missing"),
  ]);
  if (searches === 0 && recorded === 0) await track(supabase, userId, "search_intent_missing", {});
}
