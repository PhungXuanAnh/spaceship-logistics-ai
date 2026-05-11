"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, getViewAs } from "@/lib/api";
import { ChartRender } from "@/components/Charts";
import { FilterBar, Filters } from "@/components/FilterBar";

function pct(x: number | null | undefined) {
  if (x == null) return "—";
  return `${(x * 100).toFixed(1)}%`;
}
function num(x: number | null | undefined) {
  if (x == null) return "—";
  return x.toLocaleString();
}

export default function DashboardPage() {
  const [filters, setFilters] = useState<Filters>({});
  const params = useMemo(() => filters as Record<string, string>, [filters]);

  const kpis = useQuery({ queryKey: ["kpis", params, getViewAs()], queryFn: () => api.kpis(params) });
  const oot = useQuery({ queryKey: ["oot", params, getViewAs()], queryFn: () => api.ordersOverTime("week", params) });
  const status = useQuery({ queryKey: ["status", params, getViewAs()], queryFn: () => api.breakdown("status", params) });
  const carrier = useQuery({ queryKey: ["carrier", params, getViewAs()], queryFn: () => api.top("carrier", "delay_rate", 5, params) });
  const region = useQuery({ queryKey: ["region", params, getViewAs()], queryFn: () => api.breakdown("region", params) });

  const k = kpis.data || {};

  return (
    <div className="space-y-6">
      <FilterBar value={filters} onChange={setFilters} />

      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Kpi label="Total orders" value={num(k.total_orders)} />
        <Kpi label="Delivered" value={num(k.delivered_orders)} accent="text-accent2" />
        <Kpi label="Delayed" value={num(k.delayed_orders)} accent="text-danger" />
        <Kpi label="On-time rate" value={pct(k.on_time_delivery_rate)} accent="text-accent2" />
        <Kpi label="Avg delivery (days)" value={k.avg_delivery_days != null ? k.avg_delivery_days.toFixed(2) : "—"} />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium">Orders over time</h3>
            <span className="text-xs text-muted">weekly</span>
          </div>
          {oot.isLoading ? <Skel /> : <ChartRender type="line" data={(oot.data?.rows) || []} />}
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium">Orders by status</h3>
            <span className="text-xs text-muted">all statuses</span>
          </div>
          {status.isLoading ? <Skel /> : <ChartRender type="bar" data={transformBreakdown(status.data?.rows, "status")} />}
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium">Top 5 carriers by delay rate</h3>
            <span className="text-xs text-muted">requires ≥5 completed</span>
          </div>
          {carrier.isLoading ? <Skel /> : <ChartRender type="bar" data={transformTop(carrier.data?.rows, "carrier")} />}
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-medium">Orders by region</h3>
            <span className="text-xs text-muted">count</span>
          </div>
          {region.isLoading ? <Skel /> : <ChartRender type="bar" data={transformBreakdown(region.data?.rows, "region")} />}
        </div>
      </section>
    </div>
  );
}

function Kpi({ label, value, accent = "" }: { label: string; value: string; accent?: string }) {
  return (
    <div className="card">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${accent}`}>{value}</div>
    </div>
  );
}

function Skel() { return <div className="h-[300px] grid place-items-center text-muted text-sm">Loading…</div>; }

function transformBreakdown(rows: any[] | undefined, dim: string) {
  if (!rows) return [];
  return rows.map((r) => ({ label: r[dim] ?? r.label ?? "—", count: r.total ?? r.count ?? r.value ?? 0 }));
}
function transformTop(rows: any[] | undefined, dim: string) {
  if (!rows) return [];
  return rows.map((r) => ({
    label: r[dim] ?? r.label ?? "—",
    delay_rate: typeof r.delay_rate === "number" ? Number((r.delay_rate * 100).toFixed(1)) : 0,
  }));
}
