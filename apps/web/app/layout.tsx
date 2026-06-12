import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { Toaster } from "@/components/ui/toast";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SITE_NAME, SITE_URL } from "@/lib/site";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  // Google Search Console ownership proof (URL-prefix property for
  // https://checkwise.com.mx). Emits
  // <meta name="google-site-verification" content="..."> site-wide.
  // Keep this in place permanently — removing it un-verifies the
  // property.
  verification: {
    google: "OM2B1MII7_akMeN8QrPvNx-mGx6x3bH70sTF1jQW0Wc",
  },
  title: {
    default: "CheckWise · Plataforma de cumplimiento REPSE",
    template: `%s · ${SITE_NAME}`,
  },
  description:
    "CheckWise es el software de cumplimiento REPSE para empresas y proveedores en México: calendario de obligaciones, expediente auditable, revisión humana y reportes asistidos por IA.",
  applicationName: SITE_NAME,
  keywords: [
    "REPSE",
    "cumplimiento REPSE",
    "plataforma REPSE",
    "software REPSE",
    "control documental REPSE",
    "registro REPSE",
    "servicios especializados",
    "proveedores",
    "obligaciones patronales",
    "responsabilidad solidaria",
    "STPS",
    "IMSS",
    "INFONAVIT",
    "ICSOE",
    "SISUB",
    "subcontratación",
    "México",
  ],
  openGraph: {
    type: "website",
    siteName: SITE_NAME,
    locale: "es_MX",
    url: SITE_URL,
    title: "CheckWise · Plataforma de cumplimiento REPSE",
    description:
      "Calendario de obligaciones, expediente auditable, revisión humana y reportes asistidos por IA para el cumplimiento REPSE de tus proveedores.",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "CheckWise · Powered by Legal Shelf",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "CheckWise · Plataforma de cumplimiento REPSE",
    description:
      "Calendario de obligaciones, expediente auditable, revisión humana y reportes asistidos por IA para el cumplimiento REPSE de tus proveedores.",
    images: ["/og.png"],
  },
  icons: { icon: "/favicon.png" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="antialiased">
        <TooltipProvider delayDuration={300} skipDelayDuration={150}>
          {children}
        </TooltipProvider>
        <Toaster />
      </body>
    </html>
  );
}
