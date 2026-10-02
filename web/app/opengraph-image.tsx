import { ImageResponse } from "next/og";

// F7, punto 11: the preview when the landing is shared (§51: comunidades,
// grupos, contenido corto). The §50 example alert.
export const alt = "S Auto · eseauto.com.ar: 🔥 Nueva oportunidad — Ford Fiesta Titanium 2017, 88/100, 8% debajo de publicaciones comparables";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 80px",
          background: "#fafafa",
          color: "#171717",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", width: 560 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 36, fontWeight: 700 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 56,
                height: 56,
                borderRadius: 12,
                background: "#171717",
                color: "#ffffff",
              }}
            >
              S
            </div>
            S Auto
          </div>
          <div style={{ marginTop: 10, fontSize: 22, color: "#525252" }}>eseauto.com.ar</div>
          <div style={{ marginTop: 40, fontSize: 60, fontWeight: 700, lineHeight: 1.1 }}>
            Decinos cuál. Te avisamos cuando aparezca.
          </div>
          <div style={{ marginTop: 24, fontSize: 28, color: "#525252" }}>
            Te avisamos cuando aparece un auto que vale la pena mirar.
          </div>
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            width: 440,
            padding: 40,
            borderRadius: 28,
            background: "#ffffff",
            border: "2px solid #e5e5e5",
            fontSize: 26,
          }}
        >
          <div style={{ color: "#c2410c", fontWeight: 600 }}>🔥 Nueva oportunidad</div>
          <div style={{ marginTop: 12, fontSize: 34, fontWeight: 700 }}>Ford Fiesta Titanium 2017</div>
          <div style={{ marginTop: 8, color: "#525252" }}>112.000 km · USD 10.300</div>
          <div style={{ display: "flex", alignItems: "baseline", marginTop: 28 }}>
            <span style={{ fontSize: 72, fontWeight: 700 }}>88</span>
            <span style={{ marginLeft: 8, color: "#737373" }}>/ 100</span>
          </div>
          <div style={{ marginTop: 8, color: "#525252" }}>8% debajo de publicaciones comparables.</div>
        </div>
      </div>
    ),
    size,
  );
}
