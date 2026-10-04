import { Sparkles } from "lucide-react";
import type { Metadata } from "next";

import { AssistedSearch } from "@/components/app/assisted-search";
import { SearchForm } from "@/components/app/search-form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { requireUser } from "@/lib/auth";
import type { SearchValues } from "@/lib/search-form";
import { createClient } from "@/lib/supabase/server";

import { loadFormData } from "../form-data";

export const metadata: Metadata = { title: "Nueva búsqueda" };

export default async function NewSearchPage() {
  await requireUser();
  const supabase = await createClient();
  const { catalog, sources, defaultFrequency } = await loadFormData(supabase);

  const initial: SearchValues = {
    name: "",
    make: "",
    model: "",
    trim: "",
    trim_strict: false,
    year_min: null,
    year_max: null,
    price_max: null,
    currency: "USD",
    km_max: null,
    transmission: "",
    fuel: "",
    sources: sources.map((s) => s.id),
    location: null,
    km_target: null,
    price_target: null,
    seller_type: "",
    notification_frequency: defaultFrequency,
    notify_min_level: "good",
  };

  return (
    <div className="space-y-5">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Nueva búsqueda</h1>
        <p className="text-sm text-muted-foreground">Decinos qué auto estás buscando. Ese Auto monitorea por vos.</p>
      </div>
      <Tabs defaultValue="assisted">
        <TabsList>
          <TabsTrigger value="structured">Estructurado</TabsTrigger>
          <TabsTrigger value="assisted">
            <Sparkles aria-hidden /> Asistido
          </TabsTrigger>
        </TabsList>
        <TabsContent value="structured" className="pt-3">
          <SearchForm
            catalog={catalog}
            sources={sources}
            initial={initial}
            profileId={null}
          />
        </TabsContent>
        <TabsContent value="assisted" className="pt-3">
          <AssistedSearch catalog={catalog} sources={sources} base={initial} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
