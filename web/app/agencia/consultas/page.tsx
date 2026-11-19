import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { type InboxLead, LeadInbox } from "@/components/agencia/lead-inbox";
import { webConfig } from "@/lib/config";
import { channelOn } from "@/lib/dealer-program";
import { dealerLeads, myDealer } from "@/lib/dealer-server";
import { dateTime, vehicle } from "@/lib/format";

export const metadata: Metadata = { title: "Consultas" };

/** dealer_leads, read through RLS: only the leads buyers made for this agency's cars, with their consent. */
export default async function LeadsPage() {
  const [dealer, { dealerProgram }] = await Promise.all([myDealer(), webConfig()]);
  if (!dealer) redirect("/agencia");
  const leads = await dealerLeads(dealer.id);
  const rows: InboxLead[] = leads.map((l) => ({
    id: l.id,
    vehicle: l.listings ? vehicle(l.listings) : "Auto",
    listingId: l.listing_id,
    name: l.buyer_name,
    phone: l.buyer_phone,
    message: l.message,
    date: dateTime(l.created_at),
    origin: l.origin,
    status: l.status,
  }));
  return (
    <div className="space-y-5">
      <div>
        <h1 className="type-heading text-[1.9rem] leading-tight">Consultas</h1>
        <p className="text-sm text-muted-foreground">Personas que tocaron «Quiero que me contacten» en uno de tus autos y aceptaron pasarte sus datos.</p>
      </div>
      {!channelOn(dealerProgram) ? (
        <p role="status" data-testid="channel-off" className="rounded-lg bg-muted p-4 text-[15px]">El canal de venta todavía no está activo.</p>
      ) : null}
      <LeadInbox leads={rows} />
    </div>
  );
}
