"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ClientIndexPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/client/dashboard");
  }, [router]);
  return null;
}
