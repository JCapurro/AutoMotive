import { GUIDE_COPY } from "@/lib/guides";
import { publishedMakeGuides } from "@/lib/guides-data";
import { guideOgImage, OG_SIZE } from "@/lib/og-guide";

export const alt = "Guías orientativas de una marca en eseauto.com.ar";
export const size = OG_SIZE;
export const contentType = "image/png";
export const revalidate = 3600;

/** The make's name and how many of its models have a guide. */
export default async function Image({ params }: { params: Promise<{ marca: string }> }) {
  const { marca } = await params;
  const models = await publishedMakeGuides(marca).catch(() => null);
  if (!models) return guideOgImage({ eyebrow: GUIDE_COPY.badge, title: GUIDE_COPY.indexTitle, line: "Qué mirar y qué preguntar antes de ver un usado." });
  const make = models[0][0].make;
  const count = models.length;
  return guideOgImage({
    eyebrow: count === 1 ? "1 modelo con guía" : `${count} modelos con guía`,
    title: GUIDE_COPY.makeTitle.replace("{make}", make),
    line: "Qué mirar y qué preguntar antes de ver uno, modelo por modelo.",
  });
}
