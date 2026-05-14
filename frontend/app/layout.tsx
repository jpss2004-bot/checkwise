import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import "./globals.css";

export const metadata: Metadata = {
  title: "CheckWise · Plataforma de cumplimiento REPSE",
  description:
    "Carga, prevalidación y revisión humana de obligaciones documentales REPSE. Powered by Legal Shelf.",
  icons: { icon: "/favicon.png" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
