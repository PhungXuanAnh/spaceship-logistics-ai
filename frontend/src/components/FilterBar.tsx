"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Filters = {
  date_from?: string;
  date_to?: string;
  carrier?: string;
  region?: string;
  category?: string;
};

export function FilterBar({ value, onChange }: { value: Filters; onChange: (f: Filters) => void }) {
  const [carriers, setCarriers] = useState<string[]>([]);
  const [regions, setRegions] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    Promise.all([
      api.distinct("carrier"),
      api.distinct("region"),
      api.distinct("category"),
    ]).then(([c, r, ca]) => {
      setCarriers(c.values || []);
      setRegions(r.values || []);
      setCategories(ca.values || []);
    }).catch(() => {});
  }, []);

  function set<K extends keyof Filters>(k: K, v: string) {
    onChange({ ...value, [k]: v || undefined });
  }

  return (
    <div className="card grid grid-cols-2 md:grid-cols-5 gap-3">
      <div>
        <div className="label mb-1">From</div>
        <input type="date" className="input" value={value.date_from || ""} onChange={(e) => set("date_from", e.target.value)} />
      </div>
      <div>
        <div className="label mb-1">To</div>
        <input type="date" className="input" value={value.date_to || ""} onChange={(e) => set("date_to", e.target.value)} />
      </div>
      <div>
        <div className="label mb-1">Carrier</div>
        <select className="input" value={value.carrier || ""} onChange={(e) => set("carrier", e.target.value)}>
          <option value="">All</option>
          {carriers.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <div className="label mb-1">Region</div>
        <select className="input" value={value.region || ""} onChange={(e) => set("region", e.target.value)}>
          <option value="">All</option>
          {regions.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <div className="label mb-1">Category</div>
        <select className="input" value={value.category || ""} onChange={(e) => set("category", e.target.value)}>
          <option value="">All</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
    </div>
  );
}

export type { Filters };
