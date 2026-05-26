import type { ReactNode } from "react";

export default function PlatformLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-screen bg-background">{children}</div>;
}
