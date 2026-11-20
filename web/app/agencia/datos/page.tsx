import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { DealerAlertsToggle } from "@/components/agencia/dealer-alerts-toggle";
import { DealerProfileForm, type DealerFormValues } from "@/components/agencia/dealer-profile-form";
import { DealerSourceForm } from "@/components/agencia/dealer-source-form";
import { webConfig } from "@/lib/config";
import { myDealer } from "@/lib/dealer-server";
import { createClient } from "@/lib/supabase/server";

export const metadata: Metadata = { title: "Datos" };

const SOURCE_STATUS: Record<string, string> = { pending: "Lo estamos revisando", approved: "Sincronizado", rejected: "No lo pudimos sumar" };

/** «Leímos 17 autos de tu perfil»: the last whole read of a Mercado Libre profile; null before the first one. */
function profileReadText(read: { profile_read_at: string | null; profile_count: number | null } | undefined): string | null {
  if (!read?.profile_read_at || read.profile_count == null) return null;
  return read.profile_count === 1 ? "Leímos 1 auto de tu perfil" : `Leímos ${read.profile_count} autos de tu perfil`;
}

/** The agency's data and the sources it already publishes on (sync = listings we already read, once approved). */
export default async function DealerDataPage() {
  const dealer = await myDealer();
  if (!dealer) redirect("/agencia");
  const supabase = await createClient();
  const [{ data: sources }, { data: prefs }, { dealerProgram }, { data: reads }] = await Promise.all([
    supabase.from("sources").select("id, name").eq("enabled", true).neq("id", "directo").order("name"),
    supabase.from("dealers").select("alerts_email").eq("id", dealer.id).maybeSingle(),
    webConfig(),
    // The whole-profile read of each source (20270105120000): how many cars we saw there.
    supabase.from("dealer_sources").select("id, profile_read_at, profile_count").eq("dealer_id", dealer.id),
  ]);
  const profileRead = new Map((reads ?? []).map((r) => [r.id, r]));
  const names = new Map((sources ?? []).map((s) => [s.id, s.name]));
  const digits = dealer.whatsapp ?? "";
  const initial: DealerFormValues = {
    name: dealer.name,
    locality: { label: dealer.locality_label, lat: dealer.lat, lon: dealer.lon },
    phone: dealer.phone ?? "",
    // Stored with 549: shown as typed in Argentina.
    whatsapp: digits.startsWith("549") ? digits.slice(3) : digits,
    contactEmail: dealer.contact_email ?? "",
    addressText: dealer.address_text ?? "",
    links: dealer.profile_links,
  };

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <h1 className="type-heading text-[1.9rem] leading-tight">Datos de la agencia</h1>
        <DealerProfileForm mode="update" initial={initial} />
      </section>
      {dealerProgram.alertsEnabled ? (
        <section className="space-y-3" id="avisos">
          <h2 className="type-heading text-[21px] leading-tight">Avisos de tu stock</h2>
          <DealerAlertsToggle initial={prefs?.alerts_email ?? true} every={dealerProgram.alertsEveryHours} />
        </section>
      ) : null}
      <section className="space-y-4">
        <div>
          <h2 className="type-heading text-[21px] leading-tight">¿Ya publicás en otro sitio?</h2>
          <p className="text-sm text-muted-foreground">
            Si tus autos ya están en Mercado Libre, Facebook u otro sitio que leemos, los sumamos a tu stock sin cargarlos de nuevo.
            Solo entran los modelos que alguien busca.
          </p>
        </div>
        {dealer.sources.length ? (
          <ul className="border-t" data-testid="dealer-sources">
            {dealer.sources.map((s) => (
              <li key={s.id} className="flex flex-wrap items-baseline justify-between gap-x-4 border-b py-2.5 text-sm">
                <span className="min-w-0">
                  <b className="font-semibold">{names.get(s.source) ?? s.source}</b>
                  {s.seller_name_hint ? ` · ${s.seller_name_hint}` : ""}
                  {s.profile_url ? <span className="block truncate text-xs text-muted-foreground">{s.profile_url}</span> : null}
                  {profileReadText(profileRead.get(s.id)) ? (
                    <span className="block text-xs text-muted-foreground" data-testid="source-profile-read">{profileReadText(profileRead.get(s.id))}</span>
                  ) : null}
                </span>
                <span className="text-muted-foreground">{SOURCE_STATUS[s.status] ?? s.status}</span>
              </li>
            ))}
          </ul>
        ) : null}
        <DealerSourceForm sources={(sources ?? []).map((s) => ({ id: s.id, name: s.name }))} />
      </section>
    </div>
  );
}
