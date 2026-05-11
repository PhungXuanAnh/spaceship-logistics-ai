"use client";
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend, AreaChart, Area,
} from "recharts";

const colors = ["#7c5cff", "#3ddc97", "#ffb454", "#ff5670", "#5db4ff", "#c084fc"];

const tooltipStyle = {
  contentStyle: { background: "#11141b", border: "1px solid #1e2230", borderRadius: 8 },
  labelStyle: { color: "#e6e8ee" },
  itemStyle: { color: "#e6e8ee" },
};

function pickX(rows: any[]): string {
  if (!rows.length) return "x";
  const r = rows[0];
  for (const k of ["bucket", "label", "name"]) if (k in r) return k;
  return Object.keys(r)[0];
}
function pickYs(rows: any[], xKey: string): string[] {
  if (!rows.length) return [];
  return Object.keys(rows[0]).filter((k) => k !== xKey && typeof rows[0][k] === "number");
}
// Returns true iff at least one row has a numeric (non-null) value for `key`.
function keyHasNumericData(rows: any[], key: string): boolean {
  if (!rows.length || !key) return false;
  return rows.some((r) => typeof r[key] === "number" && r[key] !== null);
}

export function ChartRender({
  type, data, xKey, yKey, series,
}: { type: string; data: any[]; xKey?: string; yKey?: string; series?: string[] }) {
  if (!data || !data.length) return <div className="text-muted text-sm p-6">No data</div>;
  const x = (xKey && (xKey in data[0])) ? xKey : pickX(data);

  // Resolve y/series defensively. If the backend's chart_spec.y/series points at a key
  // that doesn't actually exist in the rows (router/analytics drift), fall back to the
  // detected numeric columns so the chart still renders something meaningful instead of
  // an empty axis.
  let ys: string[];
  if (series && series.length > 0) {
    const valid = series.filter((k) => keyHasNumericData(data, k));
    ys = valid.length > 0 ? valid : pickYs(data, x);
  } else if (yKey) {
    ys = keyHasNumericData(data, yKey) ? [yKey] : pickYs(data, x);
  } else {
    ys = pickYs(data, x);
  }

  if (type === "line") {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid stroke="#1e2230" strokeDasharray="3 3" />
          <XAxis dataKey={x} stroke="#8a91a3" fontSize={12} />
          <YAxis stroke="#8a91a3" fontSize={12} />
          <Tooltip {...tooltipStyle} />
          <Legend />
          {ys.map((k, i) => <Line key={k} type="monotone" dataKey={k} stroke={colors[i % colors.length]} dot={false} strokeWidth={2} />)}
        </LineChart>
      </ResponsiveContainer>
    );
  }

  if (type === "area") {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid stroke="#1e2230" strokeDasharray="3 3" />
          <XAxis dataKey={x} stroke="#8a91a3" fontSize={12} />
          <YAxis stroke="#8a91a3" fontSize={12} />
          <Tooltip {...tooltipStyle} />
          <Legend />
          {ys.map((k, i) => <Area key={k} dataKey={k} stroke={colors[i % colors.length]} fill={colors[i % colors.length]} fillOpacity={0.2} />)}
        </AreaChart>
      </ResponsiveContainer>
    );
  }

  if (type === "stacked_bar") {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid stroke="#1e2230" strokeDasharray="3 3" />
          <XAxis dataKey={x} stroke="#8a91a3" fontSize={12} />
          <YAxis stroke="#8a91a3" fontSize={12} />
          <Tooltip {...tooltipStyle} />
          <Legend />
          {ys.map((k, i) => <Bar key={k} dataKey={k} stackId="s" fill={colors[i % colors.length]} />)}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (type === "grouped_bar") {
    return (
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid stroke="#1e2230" strokeDasharray="3 3" />
          <XAxis dataKey={x} stroke="#8a91a3" fontSize={12} />
          <YAxis stroke="#8a91a3" fontSize={12} />
          <Tooltip {...tooltipStyle} />
          <Legend />
          {ys.map((k, i) => <Bar key={k} dataKey={k} fill={colors[i % colors.length]} />)}
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (type === "bar") {
    const yKey = ys[0] || "value";
    return (
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 8 }}>
          <CartesianGrid stroke="#1e2230" strokeDasharray="3 3" />
          <XAxis dataKey={x} stroke="#8a91a3" fontSize={12} />
          <YAxis stroke="#8a91a3" fontSize={12} />
          <Tooltip {...tooltipStyle} />
          <Bar dataKey={yKey} fill={colors[0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }

  if (type === "stat") {
    const r = data[0] || {};
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-2">
        {Object.entries(r).map(([k, v]) => (
          <div key={k} className="card">
            <div className="kpi-label">{k}</div>
            <div className="kpi-value">{typeof v === "number" ? formatNum(v) : String(v)}</div>
          </div>
        ))}
      </div>
    );
  }

  // default table
  return <DataTable rows={data} />;
}

function formatNum(n: number) {
  if (Math.abs(n) >= 1000) return n.toLocaleString();
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

export function DataTable({ rows }: { rows: any[] }) {
  if (!rows || !rows.length) return <div className="text-muted text-sm p-6">No rows</div>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="overflow-auto scrollbar max-h-96 border border-border rounded-lg">
      <table className="w-full text-sm">
        <thead className="bg-panel sticky top-0">
          <tr>{cols.map((c) => <th key={c} className="text-left px-3 py-2 border-b border-border text-muted font-medium">{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-panel/40">
              {cols.map((c) => (
                <td key={c} className="px-3 py-1.5 border-b border-border whitespace-nowrap">
                  {typeof r[c] === "number" ? formatNum(r[c]) : String(r[c] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function downloadCsv(rows: any[], filename = "data.csv") {
  if (!rows.length) return;
  const cols = Object.keys(rows[0]);
  const esc = (v: any) => {
    if (v == null) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
