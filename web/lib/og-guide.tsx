import { ImageResponse } from "next/og";

/**
 * The preview of the guides' pages when they are shared (WhatsApp, X,
 * Facebook): a page that sets its own Open Graph loses the landing's image,
 * so each guide route draws this one. The site's navy and its one yellow,
 * the eyebrow, the title and a line; no prices, no photos, no logos.
 */
export const OG_SIZE = { width: 1200, height: 630 };

export function guideOgImage({ eyebrow, title, line }: { eyebrow: string; title: string; line: string }): ImageResponse {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "64px 80px",
          background: "#ffffff",
          color: "#14213d",
          fontFamily: "sans-serif",
          borderBottom: "24px solid #ffe14d",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 34, fontWeight: 700 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 60,
              height: 60,
              borderRadius: 14,
              background: "#14213d",
              color: "#ffe14d",
            }}
          >
            S
          </div>
          eseauto.com.ar
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignSelf: "flex-start", padding: "8px 18px", borderRadius: 10, background: "#fff2a6", fontSize: 28, fontWeight: 600 }}>
            {eyebrow}
          </div>
          <div style={{ marginTop: 28, fontSize: title.length > 40 ? 64 : 76, fontWeight: 800, lineHeight: 1.05, maxWidth: 1040 }}>{title}</div>
          <div style={{ marginTop: 24, fontSize: 30, color: "#4a5468", maxWidth: 1000 }}>{line}</div>
        </div>
      </div>
    ),
    OG_SIZE,
  );
}
