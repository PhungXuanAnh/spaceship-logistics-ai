"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, getViewAs, setToken, setViewAs } from "@/lib/api";

export default function ShellLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [me, setMe] = useState<any>(null);
  const [view, setView] = useState<string>(getViewAs() || "");
  const [clients, setClients] = useState<string[]>([]);

  useEffect(() => {
    const t = typeof window !== "undefined" ? localStorage.getItem("ss_token") : null;
    if (!t) { router.replace("/login"); return; }
    api.me().then(setMe).catch(() => { setToken(null); router.replace("/login"); });
  }, [router]);

  useEffect(() => {
    if (me?.is_admin) {
      api.distinct("client_id").then((r) => setClients(r.values || [])).catch(() => {});
    }
  }, [me]);

  function applyView(v: string) {
    setView(v);
    setViewAs(v || null);
    if (typeof window !== "undefined") window.location.reload();
  }

  function logout() {
    setToken(null); setViewAs(null); router.replace("/login");
  }

  const tab = (href: string, label: string) => (
    <Link href={href} className={`tab ${pathname === href ? "tab-active" : ""}`}>{label}</Link>
  );

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-border bg-panel/40 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-4">
          <Link href="/dashboard" className="font-semibold">🛰 Spaceship Logistics AI</Link>
          <nav className="flex items-center gap-1 ml-4">
            {tab("/dashboard", "Dashboard")}
            {tab("/ask", "Ask AI")}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            {me?.is_admin && (
              <div className="flex items-center gap-2">
                <span className="text-muted text-xs">View as</span>
                <select
                  className="input py-1 w-44"
                  value={view}
                  onChange={(e) => applyView(e.target.value)}
                >
                  <option value="">All clients (admin)</option>
                  {clients.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
            )}
            {me && <span className="text-muted">{me.email}{me.is_admin ? " (admin)" : ""}</span>}
            <button className="btn-ghost" onClick={logout}>Sign out</button>
          </div>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto p-6">{children}</main>
      <footer className="border-t border-border text-xs text-muted py-3 text-center">
        Spaceship Logistics AI · demo build
      </footer>
    </div>
  );
}
