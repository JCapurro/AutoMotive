import { GUIDE_COPY, guideName, modelYears, yearsText } from "@/lib/guides";
import { publishedModelGuides } from "@/lib/guides-data";
import { guideOgImage, OG_SIZE } from "@/lib/og-guide";

export const alt = "Guía orientativa de un modelo usado en eseauto.com.ar";
export const size = OG_SIZE;
export const contentType = "image/png";
export const revalidate = 3600;

/** The model's name and years; a model that isn't published gets the guides' generic card. */
export default async function Image({ params }: { params: Promise<{ marca: string; modelo: string }> }) {
  const { marca, modelo } = await params;
  const guides = await publishedModelGuides(marca, modelo).catch(() => null);
  if (!guides) return guideOgImage({ eyebrow: GUIDE_COPY.badge, title: GUIDE_COPY.indexTitle, line: "Qué mirar y qué preguntar antes de ver un usado." });
  const { make, model } = guides[0];
  const years = modelYears(guides);
  const span = yearsText(years.from, years.to);
  return guideOgImage({
    eyebrow: GUIDE_COPY.badge,
    title: `${guideName(make, model)} usado${span ? ` ${span}` : ""}`,
    line: "Fallas conocidas, qué revisar en la visita y qué preguntarle al vendedor.",
  });
}
