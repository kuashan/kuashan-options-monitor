# Options Monitor Read-only Container Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Package the existing read-only Options Monitor Web observer as an immutable `linux/arm64` GHCR image and prepare it for a new isolated private Coolify Application.

**Architecture:** Preserve the observer's existing HTTP contract and add only a deployment-safe host argument. Build a minimal image containing `standalone_web` and its public-market-data dependency, publish it from GitHub Actions by commit SHA, and provide an image-only Compose handoff with internal port `8765` and no host ports.

**Tech Stack:** Python 3.12, stdlib `http.server`, yfinance, Docker Buildx, GitHub Actions, GHCR, Coolify image deployment.

**Spec:** `docs/superpowers/specs/2026-10-09-options-monitor-readonly-container-design.md`

## Global Constraints

- Source branch remains `feature/options-monitor-v1-final`.
- The deployed module is read-only; no broker, credentials, orders, strategy execution, or trading-state writes.
- Existing 5s, Freqtrade, daily-stock-analysis, SiftAlpha staging, and shared infrastructure are not modified.
- Oracle pulls an immutable GHCR image; Oracle does not build application source.
- The container exposes only internal port `8765`; no host port is published.
- Existing V1 tests and syntax checks remain required CI gates.
- The image must be built for `linux/arm64` from a pinned multi-architecture Python 3.12 base digest.

## Review Focus

- Host binding: local default remains loopback while the container can bind `0.0.0.0`; test this in Task 1.
- Write boundary: POST and account/order routes stay denied; preserve and extend the existing HTTP tests in Task 1.
- Image contents: credentials, `.env`, runtime databases, and unrelated full-repository state never enter the image; pin the file list in Task 2.
- Container reachability: health check targets `/api/v1/health` on internal port `8765` without publishing a host port; verify Compose and smoke behavior in Task 2.
- Artifact identity: GHCR tag and digest must point to the tested commit, with package write permission limited to the workflow; verify in Task 3.

---

### Task 1: Add a deployment-safe host binding contract

**Files:**
- Modify: `standalone_web/server.py`
- Test: `standalone_web/tests/test_server.py`

**Interfaces:**
- Consumes: existing `main()` CLI and `ThreadingHTTPServer` construction.
- Produces: `--host` CLI argument with default `127.0.0.1`; the existing `--port` validation remains unchanged.

- [ ] **Step 1: Write the failing test**

Add a focused test that parses the CLI configuration or isolates server construction and proves the local default is `127.0.0.1` while an explicit `--host 0.0.0.0` is accepted. Add/retain an HTTP regression proving `/api/v1/health` works and `/api/v1/order` remains `403`; do not add a write route.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m unittest standalone_web.tests.test_server -v`  
Expected: the new host-binding assertion fails because `main()` currently has no host argument and always constructs the server on loopback.

- [ ] **Step 3: Implement the minimal host argument**

In `standalone_web/server.py`, add `parser.add_argument("--host", default="127.0.0.1")` and pass `args.host` to `ThreadingHTTPServer`. Keep the default, port bounds, security headers, route allowlist, and read-only behavior unchanged. Update the startup message to print the selected host.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m unittest standalone_web.tests.test_server standalone_web.tests.test_public_marketdata -v`  
Expected: all focused tests pass, including the host contract and write-denial checks.

- [ ] **Step 5: Commit**

```bash
git add standalone_web/server.py standalone_web/tests/test_server.py
git commit -m "feat(web): allow explicit container host binding"
```

### Task 2: Add the minimal ARM64 container and Compose handoff

**Files:**
- Create: `Dockerfile.options-monitor`
- Create: `compose.options-monitor.yml`
- Create: `.dockerignore`
- Create: `deploy/options-monitor/README.md`
- Test: `standalone_web/tests/test_container_contract.py`

**Interfaces:**
- Consumes: `python -m standalone_web.server --host 0.0.0.0 --port 8765` from Task 1 and `standalone_web/requirements-marketdata.txt`.
- Produces: image build input, image-only Compose service `options-monitor`, internal port `8765`, and health-check contract.

- [ ] **Step 1: Write failing packaging-contract tests**

Add tests that read the Dockerfile, Compose file, and `.dockerignore` as text and assert: the Dockerfile uses a pinned Python 3.12 multi-architecture base, installs only the market-data requirements, runs as a non-root user, invokes `--host 0.0.0.0 --port 8765`, the Compose service has no `ports:` host publication, exposes `8765`, has a health check for `/api/v1/health`, and the ignore rules exclude `.git`, tests, docs, secrets, `.env`, state, databases, and output directories.

- [ ] **Step 2: Run the packaging tests to verify they fail**

Run: `python -m unittest standalone_web.tests.test_container_contract -v`  
Expected: FAIL because the deployment files do not exist on the audited branch.

- [ ] **Step 3: Implement the minimal packaging files**

Create a Dockerfile that copies only the standalone Web package, static assets, and market-data requirements; installs them without development or broker dependencies; creates a non-root runtime user; and runs the server on `0.0.0.0:8765`. Resolve and record one official `python:3.12-slim-bookworm` ARM64-capable digest. Create an image-only Compose service with `expose: ["8765"]`, no `ports`, no host volumes, a health check, and read-only runtime settings that do not prevent Python/yfinance startup. Keep the deployment README explicit that the service is read-only and requires private proxy access.

- [ ] **Step 4: Run packaging and existing tests**

Run: `python -m unittest standalone_web.tests.test_container_contract standalone_web.tests.test_server standalone_web.tests.test_public_marketdata standalone_web.tests.test_options_v1_integration -v`  
Run: `python -m compileall -q standalone_web research/four_leg_score`  
Run: `node --check standalone_web/static/app.js`  
Run: `docker compose -f compose.options-monitor.yml config`  
Expected: all commands pass; rendered Compose contains no host port binding and uses internal port `8765`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile.options-monitor compose.options-monitor.yml .dockerignore deploy/options-monitor/README.md standalone_web/tests/test_container_contract.py
git commit -m "feat(deploy): package read-only options monitor image"
```

### Task 3: Add GitHub Actions ARM64 GHCR publishing

**Files:**
- Create: `.github/workflows/options-monitor-arm64-image.yml`
- Modify: `.github/workflows/options-monitor-v1-final-ci.yml` only if a shared test command is needed; preserve all existing checks.
- Test: `standalone_web/tests/test_workflow_contract.py`

**Interfaces:**
- Consumes: Tasks 1–2 files and the existing V1 acceptance test commands.
- Produces: a GHCR image tagged with the source commit SHA and a workflow summary containing the pushed image digest.

- [ ] **Step 1: Write the failing workflow-contract test**

Add a test that verifies the workflow triggers on `feature/options-monitor-v1-final` and manual dispatch, grants only `contents: read` and `packages: write`, invokes the existing V1 test/syntax checks, builds `linux/arm64`, logs into GHCR using `GITHUB_TOKEN`, pushes an image tagged with `${{ github.sha }}`, and emits the digest.

- [ ] **Step 2: Run the workflow-contract test to verify it fails**

Run: `python -m unittest standalone_web.tests.test_workflow_contract -v`  
Expected: FAIL because the ARM64 publishing workflow does not exist.

- [ ] **Step 3: Implement the workflow**

Create the workflow using checkout, setup-python, the existing acceptance commands, Docker Buildx, GHCR login, and `docker/build-push-action`. Set `platforms: linux/arm64`, push only after tests pass, tag the image with the exact commit SHA, and write the resulting digest to the workflow summary. Do not embed any credential other than the short-lived GitHub Actions token.

- [ ] **Step 4: Run all local checks**

Run the complete existing workflow-equivalent commands plus the new contract tests and `git diff --check`. Expected: all tests, Python compile, JavaScript syntax, packaging contract, workflow contract, and formatting checks pass.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/options-monitor-arm64-image.yml standalone_web/tests/test_workflow_contract.py
git commit -m "ci(deploy): build options monitor arm64 image"
```

### Task 4: GitHub build and artifact verification

**Files:**
- No production source changes.
- Verify: GitHub Actions run, GHCR manifest, and image digest.

- [ ] **Step 1: Push the implementation branch**

Push only `feature/options-monitor-v1-final` after the local suite is green. Do not push to `main` and do not modify unrelated repositories.

- [ ] **Step 2: Verify the workflow run**

Confirm the run uses the pushed source HEAD and reaches success. Record the run ID, tested commit, image reference, and digest.

- [ ] **Step 3: Verify the image manifest**

Confirm the immutable digest contains a native `linux/arm64` manifest and that the image command, internal port, health check, and read-only route contract match Tasks 1–3. Do not deploy it yet.

### Task 5: Isolated Coolify/SiftAlpha deployment acceptance

**Files:**
- No further source changes unless a verified packaging defect is found.

- [ ] **Step 1: Create one new Coolify Application from the immutable image**

Use the existing official Coolify API with the GHCR image digest, internal port `8765`, and no host-port binding. Do not reuse any existing Application UUID.

- [ ] **Step 2: Verify runtime health and route boundaries**

Confirm the container is running, `/api/v1/health` returns `200`, `/` is reachable through the private route, `/api/v1/order` remains `403`, and no broker credential or order endpoint is present.

- [ ] **Step 3: Register the module in SiftAlpha**

Only after Coolify runtime acceptance, add a catalog record for the new isolated module and verify SiftAlpha private Open. Confirm existing projects and shared infrastructure are unchanged.

- [ ] **Step 4: Stop and report the immutable deployment identity**

Record the Coolify Application UUID, SiftAlpha project ID, private URL, source commit, GHCR digest, and runtime checks. Do not begin project deletion or trading lifecycle work.

