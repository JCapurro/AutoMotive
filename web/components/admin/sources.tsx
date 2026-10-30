import { SourceForm } from "@/components/admin/source-form";
import { EmptyRow, Pill, Table, Td, Th } from "@/components/admin/ui";
import { count, percent, when } from "@/lib/admin-format";
import type { Database } from "@/types/database";

type SourceHealth = Database["public"]["Views"]["admin_source_health"]["Row"];
type SellerCoverage = Database["public"]["Views"]["admin_seller_coverage"]["Row"];

function lastLine(text: string): string {
  return text.trim().split("\n").pop() ?? text;
}

/** admin_source_health: state, the last 24 h of collector_runs and the failure streak. */
export function SourceHealthTable({ rows, editable, alertAfter = 3 }: { rows: SourceHealth[]; editable?: boolean; alertAfter?: number }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Fuente</Th>
          <Th>Estado</Th>
          <Th numeric>Fallas seguidas</Th>
          <Th>Última OK</Th>
          <Th numeric>Corridas 24 h</Th>
          <Th numeric>Encontrados · nuevos · act.</Th>
          <Th numeric>Duración media</Th>
          <Th>Último error</Th>
          {editable ? <Th>Cadencia</Th> : null}
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => {
          const failures = s.consecutive_failures ?? 0;
          return (
            <tr key={s.id}>
              <Td className="font-medium whitespace-nowrap">
                <a href={`/admin/sources?source=${s.id}`} className="hover:underline">
                  {s.name}
                </a>
              </Td>
              <Td>
                {!s.enabled ? (
                  <Pill>Deshabilitada</Pill>
                ) : failures >= alertAfter ? (
                  <Pill tone="bad">✗ Caída</Pill>
                ) : failures > 0 ? (
                  <Pill tone="warn">! Fallando</Pill>
                ) : (
                  <Pill tone="ok">✓ OK</Pill>
                )}
              </Td>
              <Td numeric>{count(failures)}</Td>
              <Td className="whitespace-nowrap">{when(s.last_ok_at)}</Td>
              <Td numeric>
                {count(s.runs_24h)}
                {s.failed_24h ? <span className="block text-xs text-red-700">{count(s.failed_24h)} fallidas</span> : null}
              </Td>
              <Td numeric className="whitespace-nowrap">
                {count(s.found_24h)} · {count(s.new_24h)} · {count(s.updated_24h)}
              </Td>
              <Td numeric>{s.avg_seconds_24h != null ? `${s.avg_seconds_24h} s` : "—"}</Td>
              <Td className="max-w-64">
                {s.last_run_status === "failed" && s.last_error ? (
                  <span className="line-clamp-2 font-mono text-xs text-muted-foreground" title={s.last_error}>
                    {lastLine(s.last_error)}
                  </span>
                ) : (
                  "—"
                )}
              </Td>
              {editable ? (
                <Td>
                  <SourceForm id={s.id ?? ""} enabled={Boolean(s.enabled)} interval={s.crawl_interval_seconds ?? 600} />
                </Td>
              ) : null}
            </tr>
          );
        })}
        {!rows.length ? <EmptyRow colSpan={editable ? 9 : 8} /> : null}
      </tbody>
    </Table>
  );
}

/** F-02 paso 1, admin_seller_coverage: per source, the active listings without a seller type, name or key, and how many are over app_config.seller_classification.min_listings. */
export function SellerCoverageTable({ rows }: { rows: SellerCoverage[] }) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Fuente</Th>
          <Th numeric>Activos</Th>
          <Th numeric>% sin tipo</Th>
          <Th numeric>% sin nombre</Th>
          <Th numeric>% sin clave</Th>
          <Th numeric>Sobre el umbral</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.source}>
            <Td className="font-medium whitespace-nowrap">{r.source}</Td>
            <Td numeric>{count(r.active)}</Td>
            <Td numeric>{percent(r.seller_type_null_pct)}</Td>
            <Td numeric>{percent(r.seller_name_null_pct)}</Td>
            <Td numeric>{percent(r.seller_key_null_pct)}</Td>
            <Td numeric>{count(r.over_threshold)}</Td>
          </tr>
        ))}
        {!rows.length ? <EmptyRow colSpan={6} /> : null}
      </tbody>
    </Table>
  );
}
