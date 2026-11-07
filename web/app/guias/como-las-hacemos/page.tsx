import type { Metadata } from "next";
import Link from "next/link";

import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { contactEmail, siteUrl } from "@/lib/env";
import { breadcrumbJsonLd, GUIDE_COPY, jsonLdScript, METHOD_PATH, organizationJsonLd } from "@/lib/guides";

const TITLE = "Cómo hacemos las guías orientativas";
const DESCRIPTION =
  "De dónde sale la información de las guías de autos usados de Ese Auto, cómo se revisan las fuentes, cada cuánto se actualizan y qué no hacen.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: { canonical: METHOD_PATH },
  openGraph: { type: "article", locale: "es_AR", siteName: "eseauto.com.ar", title: TITLE, description: DESCRIPTION, url: METHOD_PATH, images: ["/guias/opengraph-image"] },
};

/**
 * GEO: what the guides are and where they come from, asked the way people
 * ask it, so a reader (or an engine weighing whether to cite them) can judge
 * them. Nothing about who reviews them or how drafts are written.
 */
const FAQ: { q: string; a: string }[] = [
  {
    q: "¿Para qué sirven las guías?",
    a: "Para llegar a ver un auto usado sabiendo qué mirar y qué preguntar. Cada guía resume, para un modelo, sus fallas conocidas, qué revisar en la visita, sus versiones y equipamiento, el mantenimiento que necesita, sus generaciones y una lista de preguntas para hacerle al vendedor.",
  },
  {
    q: "¿De dónde sale la información?",
    a: "De fichas técnicas, manuales del fabricante, notas de prensa especializada y foros de dueños. Cada guía muestra sus fuentes al final, con el link a cada una.",
  },
  {
    q: "¿Cómo se revisan las fuentes?",
    a: "Antes de publicar una guía se abre y se revisa cada una de sus fuentes. Una guía sin fuentes revisadas no se publica, y una fuente que no se revisó no aparece en la página.",
  },
  {
    q: "¿Cada cuánto se actualizan?",
    a: "Cuando cambia el contenido de una guía (por ejemplo, porque apareció un llamado a revisión o una corrección), cambia la fecha «Actualizada el» que se ve arriba de todo. Esa fecha es la del último cambio del texto, no la de la última vez que se volvió a publicar.",
  },
  {
    q: "¿Qué no hacen las guías?",
    a: "No verifican ningún auto en particular, no reemplazan la revisión de un mecánico de confianza y no dicen precios ni cuánto debería costar un auto. Son información general del modelo.",
  },
];

/** /guias/como-las-hacemos: the guides' method, in questions and answers. */
export default function GuidesMethod() {
  const faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    url: `${siteUrl}${METHOD_PATH}`,
    inLanguage: "es-AR",
    publisher: organizationJsonLd(siteUrl),
    mainEntity: FAQ.map(({ q, a }) => ({ "@type": "Question", name: q, acceptedAnswer: { "@type": "Answer", text: a } })),
  };
  const breadcrumb = breadcrumbJsonLd([
    { name: GUIDE_COPY.home, url: `${siteUrl}/` },
    { name: GUIDE_COPY.indexTitle, url: `${siteUrl}/guias` },
    { name: GUIDE_COPY.method, url: `${siteUrl}${METHOD_PATH}` },
  ]);
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader signedIn={false} page="guias" />
      <main className="mx-auto w-full max-w-3xl flex-1 space-y-8 px-4 pt-8 pb-16 sm:px-6 md:pt-12">
        {[faq, breadcrumb].map((ld, n) => (
          <script key={n} type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(ld) }} />
        ))}
        <nav aria-label="Ruta" className="text-sm text-muted-foreground">
          <Link href="/guias" className="underline underline-offset-4">{GUIDE_COPY.allGuides}</Link>
        </nav>
        <header className="space-y-4">
          <h1 className="type-display text-[2.1rem] leading-[1.05] text-balance md:text-5xl">{TITLE}</h1>
          <p className="text-[17px] leading-snug text-muted-foreground">{GUIDE_COPY.indexIntro}</p>
        </header>
        {FAQ.map(({ q, a }, n) => (
          <section key={q} aria-labelledby={`metodo-${n}`} className="space-y-2">
            <h2 id={`metodo-${n}`} className="text-xl font-semibold tracking-tight">{q}</h2>
            <p className="text-[16px] leading-relaxed">{a}</p>
          </section>
        ))}
        {contactEmail ? (
          <section aria-labelledby="metodo-error" className="space-y-2">
            <h2 id="metodo-error" className="text-xl font-semibold tracking-tight">¿Encontraste un error?</h2>
            <p className="text-[16px] leading-relaxed">
              Escribinos a <a href={`mailto:${contactEmail}`} className="underline underline-offset-4">{contactEmail}</a> con el modelo y lo que viste. Lo revisamos y, si corresponde, corregimos la guía.
            </p>
          </section>
        ) : null}
        <Link href="/guias" className="inline-flex min-h-11 items-center underline underline-offset-4">{GUIDE_COPY.allGuides}</Link>
      </main>
      <SiteFooter />
    </div>
  );
}
