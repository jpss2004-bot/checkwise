import type { Metadata } from "next";

// /login is a client component, so its metadata lives here in the
// segment layout. This is the one authenticated-adjacent route we let
// crawlers index — it is the public sign-in entry point.
export const metadata: Metadata = {
  title: "Iniciar sesión",
  description: "Accede a tu cuenta de CheckWise.",
  alternates: { canonical: "/login" },
};

export default function LoginLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
