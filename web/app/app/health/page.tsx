import type { Metadata } from "next";

import { AutoRefresh } from "@/components/app/auto-refresh";
import { when } from "@/lib/admin-format";
import { requireHealthOwner } from "@/lib/health-auth";
import { createAdminClient } from "@/lib/supabase/admin";

export const metadata: Metadata = { title: "Health de scraping", robots: { index: false, follow: false } };

const NAMES: Record<string, string> = {
  base: "Base de datos", worker: "Worker", web: "Web",
  "collector:mercadolibre": "MercadoLibre", "collector:facebook": "Facebook",
  "collector:kavak": "Kavak", "collector:v6": "V6", "collector:autocosmos": "Autocosmos",
};

export default async function HealthPage() {
  await requireHealthOwner();
  const { data: snapshot, error } = await createAdminClient().from("platform_health_checks")
    .select("checked_at, checks, email_pending, last_email_at").eq("id", 1).maybeSingle();
  // eslint-disable-next-line react-hooks/purity -- freshness at server request time
  const stale = !snapshot || Date.now() - Date.parse(snapshot.checked_at) > 12 * 60_000;
  const checks = (snapshot?.checks ?? {}) as Record<string, string | null>;
  const problems = Object.values(checks).filter(Boolean).length;
  const needsAttention = stale || problems > 0 || Boolean(error) || Boolean(snapshot?.email_pending);
  return (
    <div className="space-y-6">
      <AutoRefresh every={30_000} />
      <div className="space-y-2">
        <h1 className="type-heading text-3xl">Health de scraping</h1>
        <p className="text-sm text-muted-foreground">Chequeo cada 5 minutos. Recibís un email cuando aparece una falla y cuando se recupera.</p>
      </div>
      <div className={needsAttention ? "rounded-lg bg-amber-50 p-4 text-amber-950" : "rounded-lg bg-emerald-50 p-4 text-emerald-950"}>
        <p className="font-semibold">{error ? "No se pudo leer el chequeo" : stale ? "Sin chequeo reciente" : problems ? `${problems} componentes necesitan revisión` : snapshot?.email_pending ? "Aviso por email pendiente" : "La plataforma está funcionando"}</p>
        <p className="mt-1 text-sm">Último chequeo: {snapshot ? when(snapshot.checked_at) : "todavía no se ejecutó"}.</p>
        {stale ? <p className="mt-1 text-sm">El monitor corre en tu PC. Revisá que esté encendida y que el watchdog esté ejecutándose.</p> : null}
      </div>
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted"><tr><th className="px-4 py-3">Componente</th><th className="px-4 py-3">Estado</th><th className="px-4 py-3">Detalle</th></tr></thead>
          <tbody>
            {Object.entries(checks).map(([name, problem]) => (
              <tr key={name} className="border-t">
                <td className="px-4 py-3 font-medium whitespace-nowrap">{NAMES[name] ?? name}</td>
                <td className="px-4 py-3 whitespace-nowrap">{stale ? "Sin confirmar" : problem ? "Revisar" : "OK"}</td>
                <td className="max-w-xl px-4 py-3 whitespace-pre-wrap break-words">{problem ?? "Sin fallas detectadas en este chequeo"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!Object.keys(checks).some((name) => name.startsWith("collector:")) ? <p className="text-sm text-muted-foreground">No hay collectors con búsquedas activas para evaluar en este chequeo.</p> : null}
      <p className="text-sm text-muted-foreground">Los collectors se revisan cuando tienen búsquedas activas. Tres fallas seguidas activan el aviso; también se detectan corridas trabadas, búsquedas vencidas y corridas vacías después de haber obtenido resultados.</p>
      <p className="text-sm text-muted-foreground">{snapshot?.email_pending ? "Hay un aviso por email pendiente de envío. El próximo chequeo volverá a intentarlo." : "Sin avisos pendientes de envío."} Último aviso enviado: {snapshot?.last_email_at ? when(snapshot.last_email_at) : "todavía no hay envíos registrados"}.</p>
    </div>
  );
}
