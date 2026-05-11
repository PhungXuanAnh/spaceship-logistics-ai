# AI Usage Disclosure

The assignment asks for transparency about AI usage, so here it is.

## Short version

- All design decisions, architecture, library choices, and acceptance criteria were mine.
- I used GitHub Copilot as a fast pair for code generation/formatter — not for problem definition.
- Every line was reviewed before it landed; nothing is in the repo that I can't explain.

## Where AI helped

| Area | What AI drafted | What I owned |
|---|---|---|
| Boilerplate scaffolding | Dockerfile, `pyproject.toml`, FastAPI route stubs, Tailwind config | Stack choices, project layout, dependency pinning, env-var contract |
| Repository / SQLAlchemy filters | Filter chains and Pydantic models | Index strategy (none — 400 rows), allow-list design, `Repository` Protocol shape |
| React / Next.js components | Tailwind + Recharts component code | UX flow, the three-tab Answer / Plan / Raw-rows layout, the admin "View as" pattern |
| Forecasting math | Holt-Winters / moving-average code shape | Auto-select threshold (≥8 weeks), 80% PI choice, inventory formula (`mean + 1.65σ`), empty-series behaviour |
| Test scaffolding | pytest fixtures, parametrize patterns | What to test — KPI correctness, router behaviour on the spec questions, forecast edge cases, refusal of out-of-scope, full HTTP roundtrips |
| Terraform | EC2 / SG / EIP HCL boilerplate | Deploy architecture (single EC2 + Caddy vs ECS/ALB), cost target, tear-down semantics |
| Documentation | First drafts of README sections | Every claim cross-checked against the code; trade-off framing and "what isn't done" are mine |

## Where AI did not help

- **The plan.** What to build, what to refuse to build, and the order to build it in.
- **The architectural rules.** `analytics/` and `ai/` cannot import FastAPI or SQLAlchemy; the LLM never sees SQL; `MAX_TOOL_CALLS_PER_QUESTION = 2`. These are constraints I imposed because AI tends to write the easiest code, not the safest.
- **The v1 → v2 decision.** That came from running a real prompt suite and reading the numbers, not from a suggestion.

## Honest summary

I treated AI as a code-generation tool that's fast at typing and unreliable at deciding. The shape of the system, the trade-offs, the rejected paths, and the things that don't ship are mine.
