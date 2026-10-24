# Ishlash tartibi

Reja va qoidalar: [CLAUDE.md](CLAUDE.md), [docs/plan/README.md](docs/plan/README.md).

## O'rnatish

```bash
uv sync                      # Python 3.13 (.python-version), workspace paketlari
pnpm install                 # Node 24 (.nvmrc), pnpm (package.json → packageManager)
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Tekshiruvlar (CI bilan bir xil)

```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
uv run pytest -m benchmark                 # tezlik testlari (coverage'siz)
python3 -m unittest tests.test_all        # legacy (Python 3.8 bilan ham mos bo'lishi shart)
pnpm --filter web lint && pnpm --filter web typecheck && pnpm --filter web test && pnpm --filter web build
```

## Commit va PR

- Commit: [Conventional Commits](https://www.conventionalcommits.org/) — `feat:`, `fix:`, `docs:`, `ci:`,
  `chore:`, `refactor:`, `test:`; tavsif o'zbekcha, oxirida vazifa raqami: `feat: lot dvigateli (B1.5)`.
- Har vazifa alohida branch → PR (shablon bo'yicha) → CI yashil → merge.
- Har vazifadan keyin: `docs/plan/README.md` holati, `docs/plan/05-bosqichlar.md` belgisi, `CHANGELOG.md`.

## Versiyalar

Bog'liqliklar lock fayllarda (`uv.lock`, `pnpm-lock.yaml`) qotirilgan; CI `--locked` / `--frozen-lockfile`
bilan ishlaydi. Yangilash faqat ataylab (Dependabot PR). TypeScript 6 da: typescript-eslint TS 7 ni
qo'llamaguncha.
