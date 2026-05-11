"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function HomeRedirect() {
  const router = useRouter();
  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem("ss_token") : null;
    router.replace(t ? "/dashboard" : "/login");
  }, [router]);
  return <main className="p-6 text-muted">Loading…</main>;
}
