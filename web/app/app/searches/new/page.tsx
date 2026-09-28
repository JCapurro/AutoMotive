import { Sparkles } from "lucide-react";
import type { Metadata } from "next";

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
  const { catalog, sources, defaultOrigin, defaultFrequency } = await loadFormData(supabase);

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
    location: defaultOrigin ? { ...defaultOrigin, radius_km: 30 } : null,
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
        <p className="text-sm text-muted-foreground">Decinos qué auto estás buscando. Automotive monitorea por vos.</p>
      </div>
      <Tabs defaultValue="structured">
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
            defaultOrigin={defaultOrigin}
          />
        </TabsContent>
        <TabsContent value="assisted" className="pt-3">
          <div className="max-w-xl space-y-2 rounded-xl bg-card p-5 ring-1 ring-foreground/10">
            <p className="font-medium">Muy pronto: contanos qué buscás con tus palabras.</p>
            <p className="text-sm text-muted-foreground">
              «Busco Fiesta Titanium manual 2016 a 2018 hasta USD 11.500 y menos de 150.000 km». Automotive lo va a
              convertir en filtros que revisás antes de guardar. Mientras tanto, usá el modo estructurado.
            </p>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
