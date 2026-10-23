# O'zgarishlar jurnali

Format: [Keep a Changelog](https://keepachangelog.com/), versiyalar: [SemVer](https://semver.org/).
Yangi tizim (`packages/`, `apps/`) uchun; legacy ilova o'zgarishlari git tarixida.

## [Chiqarilmagan]

### Qo'shildi

- B0.1 Production rejasi (`docs/plan`), `CLAUDE.md`.
- B0.2 Monorepo skeleti: `packages/core` (upcore), `apps/api` (upapi, `/health`), `apps/bot` (upbot),
  `apps/web` (Vite + React + TS), `infra/`; uv va pnpm workspace'lari.
- B0.3 CI: ruff, mypy, pytest (core, api, bot), legacy testlari (Python 3.8 va 3.13), web
  lint/typecheck/test/build.
- B0.4 Kod tartibi: pre-commit (ruff, taqiqlangan fayllar, Conventional Commits), PR shabloni, Dependabot,
  `CONTRIBUTING.md`, `.python-version`, `.nvmrc`.
- B0.5 Dev muhit: `infra/compose/dev.yml` (PostgreSQL 18, api, web), `make dev`, API Dockerfile; CI'da
  compose smoke testi.
- B0.6 Legacy siyosati README'da.
