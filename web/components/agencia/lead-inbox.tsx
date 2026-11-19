"use client";

import { MessageCircle, Phone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { toast } from "sonner";

import { setLeadStatus } from "@/app/agencia/actions";
import { NativeSelect } from "@/components/ui/native-select";
import { whatsappUrl } from "@/lib/dealer-contact";
import { LEAD_ORIGIN, LEAD_STATUS } from "@/lib/dealer-insights";
import { formatArPhone, normalizeArPhone } from "@/lib/phone";

export type InboxLead = {
  id: number;
  vehicle: string;
  listingId: number | null;
  name: string;
  phone: string;
  message: string | null;
  date: string;
  origin: string;
  status: string;
};

/** The buyers who asked to be contacted, with their consent: name, phone, message. Only the agency's members read it (RLS). */
export function LeadInbox({ leads }: { leads: InboxLead[] }) {
  const router = useRouter();
  const [pending, run] = useTransition();
  if (!leads.length) {
    return <p className="rounded-lg bg-muted p-8 text-center text-sm text-muted-foreground">Todavía no tenés consultas.</p>;
  }
  return (
    <ul className="border-t-2 border-foreground" data-testid="lead-inbox">
      {leads.map((l) => {
        // An Argentine mobile as typed («11 2345-6789») gets its +54 9 for the call and WhatsApp links.
        const e164 = normalizeArPhone(l.phone);
        const tel = e164 ?? l.phone;
        const wa = whatsappUrl(e164 ? e164.slice(1) : null, `Hola ${l.name}, te escribo de la agencia por el ${l.vehicle} que viste en Ese Auto.`);
        return (
          <li key={l.id} className="grid gap-x-6 gap-y-1.5 border-b py-3.5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto]" data-testid="lead-row">
            <div className="min-w-0">
              <p className="font-bold">{l.name}</p>
              <p className="flex flex-wrap gap-x-3 text-sm">
                <a href={`tel:${tel}`} className="inline-flex items-center gap-1 underline underline-offset-2"><Phone className="size-3.5" aria-hidden /> {e164 ? formatArPhone(e164) : l.phone}</a>
                {wa ? <a href={wa} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline underline-offset-2"><MessageCircle className="size-3.5" aria-hidden /> WhatsApp</a> : null}
              </p>
            </div>
            <div className="min-w-0 text-sm">
              <p className="font-semibold">{l.vehicle}</p>
              {l.message ? <p className="whitespace-pre-line text-muted-foreground">{l.message}</p> : null}
              <p className="text-xs text-muted-foreground">{l.date} · desde {LEAD_ORIGIN[l.origin] ?? l.origin}</p>
            </div>
            <NativeSelect
              size="sm"
              aria-label={`Estado de la consulta de ${l.name}`}
              value={l.status}
              disabled={pending}
              onChange={(e) => {
                const status = e.target.value;
                run(async () => {
                  const result = await setLeadStatus(l.id, status).catch(() => ({ error: "No pudimos guardar. Probá de nuevo." }));
                  if (result.error) toast.error(result.error);
                  router.refresh();
                });
              }}
            >
              {Object.entries(LEAD_STATUS).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </NativeSelect>
          </li>
        );
      })}
    </ul>
  );
}
