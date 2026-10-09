# Options Monitor read-only image deployment

This package runs the existing Options Monitor V1 standalone Web observer.
It reads public market data and exposes the four-leg reference analysis. It
does not connect to a broker, accept account credentials, submit orders, run a
strategy, or write trading state.

## Image contract

- Image: `ghcr.io/kuashan/kuashan-options-monitor:<source-commit-sha>`
- Platform: `linux/arm64`
- Internal port: `8765`
- Health endpoint: `/api/v1/health`
- Host ports: none
- Required secrets: none

The production deployment must use the digest emitted by GitHub Actions, not a
mutable tag. `compose.options-monitor.yml` is image-only so Coolify pulls the
published image instead of building application source on Oracle.

## Private access

Create a new isolated Coolify Application for this image and route it through
the existing private proxy/WireGuard path. Do not reuse an existing 5s,
Freqtrade, or daily-stock-analysis Application and do not publish port 8765 on
the host.
