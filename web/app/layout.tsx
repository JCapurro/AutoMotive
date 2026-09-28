import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Toaster } from "@/components/ui/sonner";
import { siteUrl } from "@/lib/env";

import "./globals.css";

const sans = Geist({ variable: "--font-sans", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

const DESCRIPTION =
  "Decinos qué auto estás buscando. Automotive monitorea las publicaciones y te avisa cuando aparece uno que vale la pena mirar.";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: "Automotive — Encontrá las oportunidades antes que los demás", template: "%s · Automotive" },
  description: DESCRIPTION,
  // The image comes from app/opengraph-image.tsx.
  openGraph: {
    type: "website",
    locale: "es_AR",
    siteName: "Automotive",
    title: "Automotive — Encontrá las oportunidades antes que los demás",
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
      </body>
    </html>
  );
}
