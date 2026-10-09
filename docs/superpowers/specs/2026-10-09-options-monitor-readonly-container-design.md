# Options Monitor Read-only Container Module Design

**Status:** Draft for review  
**Source branch:** `feature/options-monitor-v1-final`  
**Source HEAD audited:** `cee972d93a4573563fa62c3bb56328b567315098`

## Goal

Package the existing read-only Options Monitor Web observer as an isolated
`linux/arm64` container image, publish it to GHCR with an immutable digest,
and later expose it through a new private Coolify Application and SiftAlpha
private Open route.

## Confirmed scope

The deployed module is an observer only. It may read public market data and
calculate the existing four-leg reference score, but it must not connect to a
broker, accept account credentials, submit orders, execute strategies, or
write trading state.

The existing 5s, Freqtrade, daily-stock-analysis, SiftAlpha staging service,
shared Docker networks, and shared persistent data are outside this change.

## Architecture

```text
GitHub source commit
    -> GitHub Actions tests and ARM64 image build
    -> GHCR image digest
    -> new isolated Coolify Application
    -> private proxy / WireGuard
    -> SiftAlpha private Open
```

The Oracle host will pull and run the image; it will not build the application
source. The new Coolify Application will use an image-only deployment, an
internal container port of `8765`, no host-port publication, and no shared
project volume. Public market-data egress is allowed; no secret is required.

## Source changes required

1. Add a deployment-safe host argument to `standalone_web/server.py` while
   retaining the current local default of `127.0.0.1` and allowing the image
   entrypoint to use `0.0.0.0` inside the isolated container.
2. Add a minimal ARM64-compatible Dockerfile using a pinned Python 3.12
   multi-architecture base image. Install only
   `standalone_web/requirements-marketdata.txt`, copy only the required
   standalone Web files, and run the read-only server.
3. Add an image-only Compose definition for local validation and Coolify
   handoff. It must expose container port `8765` internally, publish no host
   ports, declare a health check for `/api/v1/health`, and use a read-only
   filesystem where compatible with the dependency runtime.
4. Add a GitHub Actions workflow that runs the existing V1 tests and syntax
   checks, builds `linux/arm64`, pushes to GHCR, and records the resulting
   immutable image digest. Oracle deployment must consume that digest.

## Security and isolation

- No broker credentials, API keys, tokens, `.env` files, databases, order
  records, or trading state enter the image.
- No POST or account/ledger API is added. Unsupported `/api/v1/*` routes remain
  denied by the existing observer contract.
- The Coolify Application is new and isolated; it must not reuse the 5s,
  Freqtrade, or daily Application UUID.
- No public host port is created. Access is only through the existing private
  management path.
- The container runs as a non-root user where the runtime permits, drops
  unnecessary privileges, and has no write access to host project data.

## Deployment sequence

1. Validate the source commit and existing V1 test suite.
2. Build and publish the ARM64 image in GitHub Actions.
3. Verify image digest, manifest, health endpoint, and denied write routes.
4. Create one new isolated Coolify Application from the immutable image
   digest.
5. Verify container health and private route without touching existing
   projects.
6. Register the new read-only module in SiftAlpha only after runtime checks
   pass.

No production deployment, project lifecycle action, or existing service
modification is part of the implementation stage.

## Acceptance criteria

- Existing Options Monitor V1 tests remain passing.
- New container smoke tests prove the health endpoint works and account/order
  routes remain unavailable.
- GitHub Actions produces a `linux/arm64` image and publishes its digest.
- The image starts without credentials and does not require a broker.
- Coolify receives only the immutable image reference and internal port.
- No host port is published and private Open reaches the health and Web routes.
- Existing 5s, Freqtrade, daily-stock-analysis, SiftAlpha staging, WireGuard,
  Xray, and shared infrastructure remain unchanged.

## Non-goals

- Converting the observer into an automated options trader.
- Adding authentication, broker integration, order APIs, persistence, or
  multi-user account management.
- Removing or modifying existing Coolify Applications.
- Building application source code on Oracle.
