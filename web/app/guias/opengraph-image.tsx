import { GUIDE_COPY } from "@/lib/guides";
import { guideOgImage, OG_SIZE } from "@/lib/og-guide";

export const alt = "Guías orientativas por modelo en eseauto.com.ar";
export const size = OG_SIZE;
export const contentType = "image/png";

/** /guias: the guides' generic card. */
export default function Image() {
  return guideOgImage({ eyebrow: GUIDE_COPY.badge, title: GUIDE_COPY.indexTitle, line: "Qué mirar y qué preguntar antes de ver un usado." });
}
