"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ChartRender, DataTable, downloadCsv } from "@/components/Charts";

const SUGGESTIONS = [
  "Which carrier has the highest delay rate this quarter?",
  "Forecast next 4 weeks of orders for Apparel category",
  "Top 5 SKUs by delivered volume in Vietnam in October",
  "Compare on-time rate by region",
];

type Tab = "answer" | "plan" | "rows";

type Intent = "query" | "forecast" | "clarify" | "refuse" | "inspect" | string;

function intentPillClass(intent: Intent): string {
  switch (intent) {
    case "query": return "pill pill-ok";
    case "forecast": return "pill pill-info";
    case "clarify": return "pill pill-warn";
    case "refuse": return "pill pill-danger";
    case "inspect": return "pill pill-info";
    default: return "pill pill-muted";
  }
}

function intentLabel(intent: Intent): string {
  switch (intent) {
    case "query": return "answered";
    case "forecast": return "forecast";
    case "clarify": return "needs info";
    case "refuse": return "refused";
    case "inspect": return "schema lookup";
    default: return String(intent);
  }
}

export default function AskPage() {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [resp, setResp] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("answer");
  const [submittedQ, setSubmittedQ] = useState<string>("");
  const [engine, setEngine] = useState<"v1" | "v2">("v2");
  const [datasetRange, setDatasetRange] = useState<[string | null, string | null] | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const answerRef = useRef<HTMLDivElement | null>(null);

  async function ask(question: string) {
    setBusy(true); setErr(null); setResp(null); setTab("answer");
    setSubmittedQ(question);
    setQ(question);
    try {
      const r = await api.ask(question, {}, engine);
      setResp(r);
    } catch (e: any) {
      setErr(e?.message || "Request failed. Check your connection and try again.");
    } finally { setBusy(false); }
  }

  // Build a follow-up prompt that tells the LLM "my answer to your
  // clarification is X". We rebuild from the ORIGINAL (un-prefixed)
  // question and merge ALL chip choices (previous + new) into one flat
  // ` — use a; b; c.` suffix, so chained chip clicks don't stack into
  // nested `Re: "Re: "Re: ..."` prompts that confuse the LLM.
  function followUpFromChip(chip: string): string {
    const { original, chips } = parseRePrompt(submittedQ);
    const allChips = [...chips, chip];
    return `Re: "${original}" — use ${allChips.join("; ")}.`;
  }

  // Parse a chained `Re: "Re: "Re: <orig>" — use a." — use b." — use c.` (or
  // the flat form `Re: "<orig>" — use a; b.`) back into the original
  // question and the ordered list of chip choices already applied.
  function parseRePrompt(s: string): { original: string; chips: string[] } {
    let cur = s.trim();
    const collected: string[] = [];
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const m = cur.match(/^Re:\s*"(.+)"\s*—\s*use\s+(.+?)\.\s*$/);
      if (!m) break;
      const layer = m[2].split(/\s*;\s*/).map((s) => s.trim()).filter(Boolean);
      // Outer layers were applied LAST, so prepend so the order is
      // oldest-first.
      collected.unshift(...layer);
      cur = m[1].trim();
    }
    return { original: cur, chips: collected };
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const v = q.trim();
    if (!v || busy) return;
    ask(v);
  }

  useEffect(() => {
    if ((busy || resp || err) && answerRef.current) {
      answerRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [busy, resp, err]);

  // Fetch dataset date range once on mount so the "demo today" badge
  // is visible BEFORE the user asks anything. This makes the dataset's
  // anchored "today" transparent (vs. silently rewriting wall-clock now).
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const info = await api.dataInfo();
        if (!cancelled) setDatasetRange(info.date_range);
      } catch {
        // Non-fatal: badge just won't render.
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* ────────── Zone 1: PROMPT ────────── */}
      <section className="zone-prompt space-y-4" aria-labelledby="ask-zone-label">
        <div className="flex items-baseline justify-between gap-3 flex-wrap">
          <div>
            <div id="ask-zone-label" className="label-zone">Your question</div>
            <h2 className="text-xl sm:text-2xl font-semibold text-text mt-1">Ask about your logistics data</h2>
          </div>
          <p className="text-xs text-muted max-w-md">
            Natural-language analytics over your orders. Falls back to a deterministic keyword router when no LLM key is configured.
          </p>
        </div>
        {/* Phase-14 engine toggle */}
        <div className="flex items-center gap-2 text-xs flex-wrap" role="group" aria-label="Engine selector">
          <span className="text-muted uppercase tracking-wider">Engine:</span>
          <div className="seg" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={engine === "v1"}
              className={engine === "v1" ? "seg-item seg-item-active" : "seg-item"}
              onClick={() => setEngine("v1")}
              disabled={busy}
            >
              v1 cascade
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={engine === "v2"}
              className={engine === "v2" ? "seg-item seg-item-active" : "seg-item"}
              onClick={() => setEngine("v2")}
              disabled={busy}
            >
              v2 native (Gemini fn-call)
            </button>
          </div>
          <span className="text-muted">
            {engine === "v1"
              ? "claude → gemini (JSON-mode + Pydantic) → keyword"
              : "gemini function_declarations (provider-enforced) → keyword"}
          </span>
        </div>
        {datasetRange && datasetRange[0] && datasetRange[1] && (
          <div
            className="text-[11px] text-muted flex items-center gap-2 flex-wrap"
            data-testid="dataset-anchor-badge"
            title='Relative phrases like "last 3 months" or "this quarter" are resolved against this dataset window, not wall-clock today.'
          >
            <span className="px-2 py-0.5 rounded border border-border bg-surface-2/40">
              Demo dataset: <strong>{datasetRange[0]}</strong> → <strong>{datasetRange[1]}</strong>
            </span>
            <span>
              "today" for relative dates = <strong>{datasetRange[1]}</strong>
            </span>
          </div>
        )}
        <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-2.5" role="search">
          <input
            ref={inputRef}
            className="input-lg flex-1"
            placeholder="e.g. Which carrier has the highest delay rate?"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Ask a question about your logistics data"
            autoFocus
            disabled={busy}
          />
          <button
            type="submit"
            className="btn-primary-lg sm:w-auto w-full"
            disabled={busy || !q.trim()}
            aria-label="Submit question"
          >
            {busy ? <><span className="spinner" aria-hidden="true" /><span className="ml-2">Asking…</span></> : "Ask"}
          </button>
        </form>
        <div role="group" aria-label="Example prompts" className="space-y-1.5">
          <div className="label-zone">Try one of these</div>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                className="suggested-chip"
                onClick={() => { setQ(s); ask(s); }}
                disabled={busy}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Empty state */}
      {!busy && !resp && !err && (
        <div className="empty-hint" ref={answerRef}>
          Ask a question above, or pick an example. The answer zone will appear here —
          with a chart, the structured plan, and the underlying rows.
        </div>
      )}

      {/* Loading state */}
      {busy && (
        <div className="zone-answer" ref={answerRef} aria-live="polite" aria-busy="true">
          <div className="flex items-center gap-3">
            <span className="spinner" aria-hidden="true" />
            <div>
              <div className="text-sm text-text font-medium">Asking the AI…</div>
              <div className="text-xs text-muted mt-0.5">Routing your question to the best provider.</div>
            </div>
          </div>
        </div>
      )}

      {/* Error state */}
      {err && (
        <div className="error-banner" role="alert" ref={answerRef}>
          <span aria-hidden="true">⚠</span>
          <div>
            <div className="font-medium">Something went wrong</div>
            <div className="opacity-90">{err}</div>
          </div>
        </div>
      )}

      {/* Metadata + Answer */}
      {resp && !busy && (
        <div className="space-y-3" ref={answerRef}>
          <div className="zone-meta" aria-label="Response metadata">
            <span className={intentPillClass(resp.intent)}>
              <span className="pill-key">intent</span>{intentLabel(resp.intent)}
            </span>
            {resp.tool_used && (
              <span className="pill pill-muted">
                <span className="pill-key">tool</span>{resp.tool_used}
              </span>
            )}
            {resp.provider_used && (
              <span className="pill pill-muted">
                <span className="pill-key">provider</span>{resp.provider_used}
              </span>
            )}
            {resp.engine && (
              <span className={resp.engine === "v2-native" ? "pill pill-info" : "pill pill-muted"}>
                <span className="pill-key">engine</span>{resp.engine}
              </span>
            )}
            {typeof resp.duration_ms === "number" && (
              <span className="pill pill-muted">
                <span className="pill-key">latency</span>{resp.duration_ms} ms
              </span>
            )}
            {typeof resp.row_count === "number" && (
              <span className="pill pill-muted">
                <span className="pill-key">rows</span>{resp.row_count}
              </span>
            )}
          </div>

          <section className="zone-answer space-y-4" aria-labelledby="answer-zone-label">
            <div>
              <div id="answer-zone-label" className="label-zone">
                {resp.intent === "clarify" ? "I need a bit more info"
                  : resp.intent === "refuse" ? "I can't answer that"
                  : resp.intent === "inspect" ? "Let me check the schema first"
                  : "Answer"}
              </div>
              {submittedQ && (() => {
                const { original, chips } = parseRePrompt(submittedQ);
                const refinedSuffix = chips.length > 0
                  ? <span className="text-muted font-normal"> (refined: {chips.join("; ")})</span>
                  : null;
                return resp.intent === "query" || resp.intent === "forecast" ? (
                  <h3 className="text-base sm:text-lg font-medium text-text mt-1 leading-snug">
                    “{original}”{refinedSuffix}
                  </h3>
                ) : (
                  <div className="text-xs text-muted mt-1">
                    You asked: <span className="text-text/80">“{original}”</span>
                    {chips.length > 0 && <span> · refined: {chips.join("; ")}</span>}
                  </div>
                );
              })()}
            </div>

            {resp.intent === "refuse" && (
              <div className="text-sm text-text">
                {resp.answer || "Out of scope. I only answer questions about your logistics data."}
              </div>
            )}

            {resp.intent === "clarify" && (
              <div className="space-y-3">
                <div className="text-sm text-text">
                  {resp.clarification?.question
                    || resp.answer
                    || "I need a bit more detail to answer this. Could you specify a time range, a metric, or a dimension?"}
                </div>
                <div role="group" aria-label="Suggested follow-ups" className="flex flex-col sm:flex-row flex-wrap gap-2">
                  {(resp.clarification?.suggested_options || resp.clarification?.chips || resp.clarification?.options || []).map((o: string) => (
                    <button
                      key={o}
                      type="button"
                      className="btn-clarify"
                      onClick={() => ask(followUpFromChip(o))}
                    >
                      {o}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {resp.intent === "inspect" && (
              <div className="space-y-3">
                {resp.answer && (
                  <div className="text-sm text-text">{resp.answer}</div>
                )}
                {Array.isArray(resp.data) && resp.data.length > 0 && (
                  <div role="group" aria-label="Available values" className="flex flex-wrap gap-2">
                    {resp.data.slice(0, 20).map((row: any) => {
                      const v = String(row.value ?? "");
                      if (!v) return null;
                      return (
                        <button
                          key={v}
                          type="button"
                          className="btn-clarify"
                          onClick={() => ask(followUpFromChip(v))}
                          title={`Re-ask with ${v}`}
                        >
                          {v}
                        </button>
                      );
                    })}
                  </div>
                )}
                <div className="text-xs text-muted">
                  Tip: pick a value above to re-run your question with it filled in.
                </div>
              </div>
            )}

            {(resp.intent === "query" || resp.intent === "forecast") && (
              <>
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="seg" role="tablist" aria-label="Answer view">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={tab === "answer"}
                      className={`seg-item ${tab === "answer" ? "seg-item-active" : ""}`}
                      onClick={() => setTab("answer")}
                    >Answer</button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={tab === "plan"}
                      className={`seg-item ${tab === "plan" ? "seg-item-active" : ""}`}
                      onClick={() => setTab("plan")}
                    >Plan</button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={tab === "rows"}
                      className={`seg-item ${tab === "rows" ? "seg-item-active" : ""}`}
                      onClick={() => setTab("rows")}
                    >Raw rows</button>
                  </div>
                  {resp.data && resp.data.length > 0 && (
                    <button
                      type="button"
                      className="btn-ghost ml-auto"
                      onClick={() => downloadCsv(resp.data, "ask_result.csv")}
                      aria-label="Download result rows as CSV"
                    >
                      Download CSV
                    </button>
                  )}
                </div>

                {tab === "answer" && (
                  <div className="space-y-3">
                    {resp.answer && (
                      <div className="text-sm text-text whitespace-pre-wrap">{resp.answer}</div>
                    )}
                    {resp.chart_spec && resp.data && (
                      <div>
                        {resp.chart_spec.title && (
                          <div className="text-xs text-muted mb-1.5">{resp.chart_spec.title}</div>
                        )}
                        <ChartRender
                          type={resp.chart_spec.type}
                          data={resp.data}
                          xKey={resp.chart_spec.x}
                          yKey={resp.chart_spec.y}
                          series={resp.chart_spec.series}
                        />
                      </div>
                    )}
                    {resp.explanation && (
                      <div className="space-y-1">
                        <div className="label-zone">Why this answer</div>
                        <div className="rationale">
                          <strong>Why:</strong> {resp.explanation}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {tab === "plan" && (
                  <pre className="text-xs bg-bg p-3 rounded-lg border border-border overflow-auto max-h-96 scrollbar text-text">
{JSON.stringify(resp.plan, null, 2)}
                  </pre>
                )}

                {tab === "rows" && <DataTable rows={resp.data || []} />}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
