import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CheckWise V1",
  description: "Base técnica para cumplimiento documental REPSE.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
