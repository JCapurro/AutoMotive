import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { GuideEditor } from "@/components/admin/guide-editor";
import { GuideStatusButton, RequestGuideButton } from "@/components/admin/guide-buttons";
import { PageHeader, Pill, TextLink } from "@/components/admin/ui";
import { requireAdmin } from "@/lib/admin";
import { loadGuide } from "@/lib/admin-guides";
import { guidePath, readBody, readQuestions, readSources, yearsText } from "@/lib/guides";

export const metadata: Metadata = { title: "Guía" };

const JOB: Record<string, string> = { queued: "en cola", running: "generando", done: "listo", failed: "falló" };

function when(iso: string | null): string {
  return iso ? new Intl.DateTimeFormat("es-AR", { dateStyle: "short", timeStyle: "short", timeZone: "America/Argentina/Buenos_Aires" }).format(new Date(iso)) : "—";
}

/** PAR-04: one guide's editor, its origin, its last job and the publish switch. */
export default async function GuideAdmin({ params }: PageProps<"/admin/guides/[id]">) {
  await requireAdmin();
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const data = await loadGuide(Number(id));
  if (!data) notFound();
  if (data.missing) return <p className="rounded-xl bg-muted p-4 text-sm">Falta aplicar la migración <code>20261205120000_par04_model_guides</code>.</p>;
  const { guide, job, timingBelt, generation } = data;
  const [provider, prompt] = (guide.llm_version ?? "").split("|");
  const origin = guide.origin === "llm"
    ? `Borrador de IA del ${when(guide.generated_at)}${provider ? `, ${provider}` : ""}${prompt ? `, ${prompt}` : ""}`
    : "Escrita a mano";

  return (
    <>
      <PageHeader
        title={`${guide.make} ${guide.model}${guide.generation_label ? ` · ${guide.generation_label}` : ""}`}
        description={`${yearsText(guide.year_from, guide.year_to) || "Todo el modelo"} · ${origin}`}
      >
        <TextLink href="/admin/guides" className="text-sm">← Guías</TextLink>
      </PageHeader>

      <div className="flex flex-wrap items-start gap-3 text-sm">
        {guide.status === "published" ? <Pill tone="ok">publicada</Pill> : <Pill tone="warn">borrador</Pill>}
        {guide.reviewed_at ? <span className="text-muted-foreground">Última revisión: {when(guide.reviewed_at)}</span> : null}
        <GuideStatusButton id={guide.id} status={guide.status} updatedAt={guide.updated_at} />
        {guide.status === "published" ? <TextLink href={guidePath(guide.slug_make, guide.slug_model)}>Ver página</TextLink> : null}
        {generation.enabled && guide.status === "draft" ? (
          <>
            <RequestGuideButton id={guide.id} />
            <RequestGuideButton id={guide.id} force />
          </>
        ) : (
          <span className="text-muted-foreground">{generation.enabled ? "Despublicala para regenerarla." : "La generación con IA está apagada."}</span>
        )}
      </div>

      <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
        <dt className="text-muted-foreground">Último borrador</dt>
        <dd>{job ? `${JOB[job.status] ?? job.status} (${when(job.created_at)})${job.status === "failed" && job.error ? `: ${job.error}` : ""}` : "—"}</dd>
        <dt className="text-muted-foreground">Distribución en el catálogo</dt>
        <dd>{timingBelt === true ? "correa" : timingBelt === false ? "cadena" : "sin dato"} <span className="text-muted-foreground">(referencia: la guía no se sincroniza con el catálogo)</span></dd>
      </dl>

      <GuideEditor
        id={guide.id}
        status={guide.status}
        updatedAt={guide.updated_at}
        initial={{
          make: guide.make, model: guide.model, generation_label: guide.generation_label, year_from: guide.year_from, year_to: guide.year_to,
          body: readBody(guide.body), questions: readQuestions(guide.questions), sources: readSources(guide.sources),
        }}
      />
    </>
  );
}
