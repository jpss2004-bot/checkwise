import type { Metadata } from "next";

// Token-gated activation flow — never useful in search results.
export const metadata: Metadata = {
  title: "Activar cuenta",
  robots: { index: false, follow: false },
};

export default function ActivateLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
