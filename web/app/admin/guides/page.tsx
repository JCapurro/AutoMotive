import type { Metadata } from "next";

import { CreateGuideButton, CreateOtherGuide, GenerateMissingButton, GuideStatusButton, RequestGuideButton } from "@/components/admin/guide-buttons";
import { EmptyRow, PageHeader, Pill, Section, Stat, Table, Td, TextLink, Th } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import { type GuideCounts, type GuideJob, type GuideRow, loadGuidesOverview } from "@/lib/admin-guides";
import { guidePath, yearsText } from "@/lib/guides";

export const metadata: Metadata = { title: "Guías" };

const JOB: Record<string, string> = { queued: "en cola", running: "generando", done: "listo", failed: "falló" };

function GuideState({ guide, pilot }: { guide: GuideRow | undefined; pilot: boolean }) {
  return (
    <span className="flex flex-wrap gap-1">
      {!guide ? <Pill>sin guía</Pill> : guide.status === "published" ? <Pill tone="ok">publicada</Pill> : <Pill tone="warn">borrador</Pill>}
      {guide ? <Pill>{guide.origin === "llm" ? "borrador de IA" : "a mano"}</Pill> : null}
      {pilot ? <Pill tone="warn">Piloto</Pill> : null}
    </span>
  );
}

function JobState({ job }: { job: GuideJob | undefined }) {
  if (!job) return <span className="text-muted-foreground">—</span>;
  return (
    <span className="space-y-0.5">
      <Pill tone={job.status === "failed" ? "bad" : job.status === "done" ? "ok" : "muted"}>{JOB[job.status] ?? job.status}</Pill>
      {job.status === "failed" && job.error ? <span className="block text-xs text-muted-foreground">{job.error}</span> : null}
    </span>
  );
}

function Counts({ c }: { c: GuideCounts | undefined }) {
  return <span className="tabular-nums">{c ? `${c.viewed} · ${c.cta_clicked} · ${c.questions_copied}` : "0 · 0 · 0"}</span>;
}

function Actions({ guide, generationOn }: { guide: GuideRow; generationOn: boolean }) {
  return (
    <div className="flex flex-wrap items-start gap-2">
      <TextLink href={`/admin/guides/${guide.id}`} className="inline-flex h-7 items-center text-sm">Editar</TextLink>
      <GuideStatusButton id={guide.id} status={guide.status} updatedAt={guide.updated_at} />
      {guide.status === "published" ? <TextLink href={guidePath(guide.slug_make, guide.slug_model)} className="inline-flex h-7 items-center text-sm">Ver página</TextLink> : null}
      {generationOn && guide.status === "draft" ? <RequestGuideButton id={guide.id} /> : null}
    </div>
  );
}

/**
 * PAR-04 /admin/guides: the 30 models with the most active searches and their
 * guide, the other guides, and the generation's switch and caps. Nothing goes
 * public until Juan publishes it here.
 */
export default async function GuidesAdmin() {
  await requireAdmin();
  const data = await loadGuidesOverview();
  if (data.missing) {
    return (
      <>
        <PageHeader title="Guías" />
        <p className="rounded-xl bg-muted p-4 text-sm">Falta aplicar la migración <code>20261205120000_par04_model_guides</code>.</p>
      </>
    );
  }
  const { candidates, guides, counts, jobs, pilot, generation } = data;
  const byModel = new Map<string, GuideRow>();
  for (const g of guides) {
    const key = `${g.make}|${g.model}`;
    const prev = byModel.get(key);
    if (!prev || (g.status === "published" && prev.status !== "published")) byModel.set(key, g);
  }
  const listed = new Set(candidates.map((c) => c.guide_id).filter(Boolean));
  const others = guides.filter((g) => !listed.has(g.id));

  return (
    <>
      <PageHeader title="Guías" description="Guías orientativas por modelo (PAR-04). Lo que genera la IA es un borrador: nada sale a la web sin que lo publiques acá." />

      <div className="grid gap-3 sm:grid-cols-3">
        <Stat label="Generación con IA" value={generation.enabled ? "Prendida" : "Apagada"}
          note={generation.enabled ? "llm_limits.model_guide.enabled" : "La generación con IA está apagada. Crear y editar a mano funciona igual."} />
        <Stat label="Borradores hoy" value={`${generation.usedToday} de ${generation.perDay}`} note="Los aciertos de cache no cuentan." />
        <Stat label="Borradores este mes" value={`${generation.usedMonth} de ${generation.perMonth}`} />
      </div>

      <Section title="Los 30 modelos con más búsquedas activas" description="Búsquedas prendidas y vigentes, por modelo del catálogo. Vistas · clics en «Crear mi búsqueda» · copias de preguntas, últimos 30 días.">
        {generation.enabled ? <GenerateMissingButton /> : null}
        <Table>
          <thead>
            <tr>
              <Th>Modelo</Th>
              <Th numeric>Búsquedas</Th>
              <Th>Guía</Th>
              <Th>Último borrador</Th>
              <Th>30 días</Th>
              <Th>Acciones</Th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => {
              const guide = byModel.get(`${c.make}|${c.model}`);
              return (
                <tr key={`${c.make}|${c.model}`} data-testid="guide-candidate">
                  <Td>
                    <span className="font-medium">{c.make} {c.model}</span>
                    <span className="block text-xs text-muted-foreground">{yearsText(c.year_from, c.year_to) || "sin años"}</span>
                  </Td>
                  <Td numeric>{c.active_searches}</Td>
                  <Td><GuideState guide={guide} pilot={guide ? pilot.has(guide.id) : false} /></Td>
                  <Td><JobState job={guide ? jobs.get(guide.id) : undefined} /></Td>
                  <Td><Counts c={guide ? counts.get(guide.id) : undefined} /></Td>
                  <Td>{guide ? <Actions guide={guide} generationOn={generation.enabled} /> : <CreateGuideButton make={c.make} model={c.model} yearFrom={c.year_from} yearTo={c.year_to} />}</Td>
                </tr>
              );
            })}
            {!candidates.length ? <EmptyRow colSpan={6}>No hay búsquedas activas con modelo.</EmptyRow> : null}
          </tbody>
        </Table>
      </Section>

      <Section title="Otras guías" description="Guías de modelos fuera de la lista, o de otras generaciones.">
        <Table>
          <thead>
            <tr>
              <Th>Modelo</Th>
              <Th>Guía</Th>
              <Th>Último borrador</Th>
              <Th>30 días</Th>
              <Th>Acciones</Th>
            </tr>
          </thead>
          <tbody>
            {others.map((g) => (
              <tr key={g.id} data-testid="guide-other">
                <Td>
                  <span className="font-medium">{g.make} {g.model}</span>
                  <span className="block text-xs text-muted-foreground">{[g.generation_label, yearsText(g.year_from, g.year_to)].filter(Boolean).join(" · ") || "todo el modelo"}</span>
                </Td>
                <Td><GuideState guide={g} pilot={pilot.has(g.id)} /></Td>
                <Td><JobState job={jobs.get(g.id)} /></Td>
                <Td><Counts c={counts.get(g.id)} /></Td>
                <Td><Actions guide={g} generationOn={generation.enabled} /></Td>
              </tr>
            ))}
            {!others.length ? <EmptyRow colSpan={5}>Ninguna.</EmptyRow> : null}
          </tbody>
        </Table>
        <CreateOtherGuide />
      </Section>
    </>
  );
}
