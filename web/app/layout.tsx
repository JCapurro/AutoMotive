import type { Metadata, Viewport } from "next";
import { Archivo, Geist_Mono } from "next/font/google";

import { MetaPixel } from "@/components/meta-pixel";
import { Toaster } from "@/components/ui/sonner";
import { siteUrl } from "@/lib/env";

import "./globals.css";

// Archivo (Omnibus-Type, Buenos Aires) with its width axis: wide headlines, narrow figures.
const sans = Archivo({ variable: "--font-sans", subsets: ["latin"], axes: ["wdth"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const DESCRIPTION =
  "Decinos qué auto estás buscando. Ese Auto monitorea las publicaciones y te avisa cuando aparece uno que vale la pena mirar.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: "eseauto.com.ar — Decinos cuál. Te avisamos cuando aparezca.", template: "%s · eseauto.com.ar" },
  description: DESCRIPTION,
  // The image comes from app/opengraph-image.tsx.
  openGraph: {
    type: "website",
    locale: "es_AR",
    siteName: "eseauto.com.ar",
    title: "eseauto.com.ar — Decinos cuál. Te avisamos cuando aparezca.",
    description: DESCRIPTION,
  },
  twitter: { card: "summary_large_image" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es-AR" className={`${sans.variable} ${mono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        {children}
        <Toaster position="top-center" richColors closeButton />
        <MetaPixel />
      </body>
    </html>
  );
}
