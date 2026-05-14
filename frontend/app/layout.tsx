import type { Metadata } from "next";
import { Open_Sans } from "next/font/google";
import "./globals.css";

const openSans = Open_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-sans",
});

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
    <html lang="es" className={openSans.variable}>
      <body className="antialiased">{children}</body>
    </html>
  );
}
