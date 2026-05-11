"use client";

// Use NEXT_PUBLIC_API_URL when set; empty string => same-origin (production behind Caddy).
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("ss_token");
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token === null) window.localStorage.removeItem("ss_token");
  else window.localStorage.setItem("ss_token", token);
}

export function setViewAs(client: string | null) {
  if (typeof window === "undefined") return;
  if (!client) window.localStorage.removeItem("ss_view_as");
  else window.localStorage.setItem("ss_view_as", client);
}

export function getViewAs(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("ss_view_as");
}

async function request(method: string, path: string, body?: any, withAuth = true) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (withAuth) {
    const t = getToken();
    if (t) headers["authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${txt}`);
  }
  return res.json();
}

export async function login(email: string, password: string) {
  const params = new URLSearchParams();
  params.set("username", email);
  params.set("password", password);
  const res = await fetch(`${API}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: params.toString(),
  });
  if (!res.ok) throw new Error("Login failed");
  const j = await res.json();
  setToken(j.access_token);
  return j;
}

export const api = {
  me: () => request("GET", "/api/auth/me"),
  kpis: (params: Record<string, string> = {}) =>
    request("GET", `/api/kpis?${qs(params)}`),
  ordersOverTime: (granularity = "week", params: Record<string, string> = {}) =>
    request("GET", `/api/charts/orders-over-time?granularity=${granularity}&${qs(params)}`),
  breakdown: (dimension: string, params: Record<string, string> = {}) =>
    request("GET", `/api/charts/breakdown?dimension=${dimension}&${qs(params)}`),
  top: (dimension: string, metric = "delay_rate", n = 5, params: Record<string, string> = {}) =>
    request("GET", `/api/charts/top?dimension=${dimension}&metric=${metric}&n=${n}&${qs(params)}`),
  ask: (question: string, params: Record<string, string> = {}, engine: "v1" | "v2" = "v1") =>
    request(
      "POST",
      `${engine === "v2" ? "/api/v2/ask" : "/api/ask"}?${qs(params)}`,
      { question },
    ),
  preview: (params: Record<string, string> = {}, limit = 50) =>
    request("GET", `/api/data/preview?limit=${limit}&${qs(params)}`),
  distinct: (column: string) => request("GET", `/api/data/distinct/${column}`),
  dataInfo: () => request("GET", "/api/data/info") as Promise<{ date_range: [string | null, string | null] }>,
};

function qs(params: Record<string, string | undefined>): string {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== "") u.set(k, v);
  });
  const view = getViewAs();
  if (view) u.set("view_as", view);
  return u.toString();
}

export { API };
