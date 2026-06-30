# `cao_mcp_apps` — MCP Apps UI surface

The browser-free, JIT-free **frontend** for CAO's [SEP-1865 "MCP Apps"](https://modelcontextprotocol.io/seps/1865-mcp-apps-interactive-user-interfaces-for-mcp)
fleet UI. Each view is built into a **single, self-contained HTML file** (all JS
and CSS inlined — no external assets) and shipped inside the Python wheel at
`src/cli_agent_orchestrator/ext_apps/apps_static/`, where the built-in `mcp_apps`
plugin serves it to an MCP App–capable host (Claude Desktop, Cursor, VS Code
Insiders, Goose).

This package is **build-time only** — Node is not required to *run* CAO. You only
need it to develop, test, or rebuild these views. For the feature overview and
host setup, see [`../docs/mcp-apps.md`](../docs/mcp-apps.md) and the
[MCP Apps section of the root README](../README.md#mcp-apps--host-rendered-fleet-ui).

## Views

| Resource URI            | Source entry                       | Built artifact         |
| ----------------------- | ---------------------------------- | ---------------------- |
| `ui://cao/dashboard`    | `src/dashboard/dashboard.html`     | `apps_static/dashboard.html` |
| `ui://cao/agent`        | `src/agent/agent.html`             | `apps_static/agent.html` |
| `ui://cao/event-stream` | `src/event-stream/event-stream.html` | `apps_static/event-stream.html` |

Shared building blocks live in `src/shared/` (the `McpApp` postMessage/JSON-RPC
bridge, status/event/task components, and the RFC-6902 patch helpers).

## Layout

```
cao_mcp_apps/
├── src/
│   ├── dashboard/      # ui://cao/dashboard view + entry
│   ├── agent/          # ui://cao/agent view + entry
│   ├── event-stream/   # ui://cao/event-stream view + entry
│   ├── shared/         # McpApp bridge, components, patch helpers, types
│   └── test/           # unit/component/integration tests + Mock Host harness
├── e2e/                # Playwright specs + standalone harness server
├── scripts/            # JIT scan, bundle-size budget, coverage ratchet, demo
├── vite.config.ts      # shared single-file build factory (+ per-view configs)
├── vitest.config.ts    # unit/component/integration test + coverage config
└── playwright.config.ts
```

## Prerequisites

- Node.js 20+ and npm.

```bash
cd cao_mcp_apps
npm install
```

## Commands

| Command | Description |
| --- | --- |
| `npm run typecheck` | `tsc --noEmit` type check. |
| `npm test` | Run the Vitest unit/component/integration suites once. |
| `npm run test:watch` | Vitest in watch mode. |
| `npm run test:e2e` | Playwright E2E (builds bundles + starts the harness server first). |
| `npm run build:all` | Build all three single-file views into `apps_static/`. |
| `npm run build:dashboard` / `build:agent` / `build:events` | Build one view. |
| `npm run scan:jit` | Fail if any built bundle contains a JIT token (`eval`/`new Function`). |
| `npm run check:size` | Enforce the per-bundle gzipped size budget. |
| `npm run coverage:ratchet` | Fail if measured coverage drops below the recorded floors. |
| `npm run demo` | Record the dashboard → agent → event-stream walk-through. |

## Design guarantees

- **Single-file output.** `vite-plugin-singlefile` inlines all JS/CSS so each view
  is one HTML document the host can load with no asset server.
- **JIT-free / no `unsafe-eval`.** Builds target `es2021` and ship no
  `eval`/`new Function`; `npm run scan:jit` fails the build if a JIT token slips
  in, which lets the bundle run under the spec's no-`unsafe-eval` CSP.
- **HTTP-only MCP boundary.** The Python guard `test/test_http_only_boundary.py`
  keeps the views talking to the backend over the audited HTTP surface only.

## CI

Two jobs in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) cover this
package:

- **CAO MCP Apps** — install → typecheck → unit tests with coverage → `build:all`
  → JIT scan → bundle-size budget → HTTP-only guard → backend coverage →
  **coverage ratchet**.
- **CAO MCP Apps E2E (Playwright)** — installs Chromium and runs the E2E specs.

### Coverage ratchet

`scripts/coverage-ratchet.mjs` reads the line-coverage floors from the
repo-root [`.coverage-baseline.json`](../.coverage-baseline.json) and fails CI if
either the Python or the frontend coverage drops below its floor (a `null` floor
is record-only). Frontend coverage comes from Vitest's `coverage-summary.json`
(`provider: "v8"`), scoped to the `coverage.include` globs in `vitest.config.ts`.

> **Note on the V8 coverage number.** Vitest 4 / `@vitest/coverage-v8` 4 compute
> V8 line coverage via AST-based remapping (replacing the older, less accurate
> `v8-to-istanbul` mapping). The reported percentage for the same tests is
> therefore lower — and more accurate — than under Vitest 2/3. If you bump these
> tooling majors, re-measure with `npx vitest run --coverage` and either add
> tests to stay above the floor or re-baseline `.coverage-baseline.json` with a
> documented rationale, rather than assuming a regression in the code itself.
