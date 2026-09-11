# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Studio Fitness — Agenda e Gestão: a Django web app (no native app, responsive web only) for a fitness studio. Its core problem is scheduling sessions that jointly reserve a **professor + eletroestimulação equipment + aluno (student)**, respecting equipment prep/cleanup time windows. Portuguese (pt-br) is the language throughout — models, views, templates, commit messages, and UI strings. Match that when adding code.

Currently in "Fase 1 / Pacote Básico".

## Commands

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # DEBUG=True, SQLite
python manage.py migrate
python manage.py popular_demo     # seeds demo data (users, plans, equipment, sample sessions)
python manage.py runserver
```

- Run all tests: `python manage.py test`
- Run tests for one app: `python manage.py test apps.agenda`
- Demo logins (password `demo1234`): `gestor`, `bia`, `leo`, `felipe` (professores), `mariana` (aluna).
- App: http://127.0.0.1:8000 — admin/cadastros (gestor only): http://127.0.0.1:8000/admin/

No test suite exists yet in the repo — when adding tests, `apps/agenda/motor.py` and `apps/agenda/servicos.py` are the highest-value targets since they hold the scheduling conflict logic.

## Architecture

### App layout (`apps/`)

Five Django apps, each owning one URL prefix mounted in `config/urls.py`:

- **`contas`** — custom user model (`Usuario`, `AUTH_USER_MODEL`) with a `papel` (role) field: `gestor`, `professor`, or `aluno`. Login/logout views only; no signup flow. `permissions.py` defines `gestor_required`, the decorator gating every cadastro/admin screen (checked via `request.user.is_gestor` / `is_superuser`, properties on `Usuario`).
- **`cadastros`** — reference data: `Equipamento`, `TipoSessao` (session type — carries `duracao_min`, `preparo_min`, `troca_min`, and `professor_no_preparo`), `Professor` (1:1 to `Usuario`, M2M to enabled `TipoSessao`), `Aluno` (optionally linked 1:1 to a `Usuario`, since a student may not have a login). Views follow one shared CRUD helper, `_crud_simples()` in `apps/cadastros/views.py`, reused across `alunos`/`equipamentos`/`tipos_sessao` — the pattern is list + inline create/update form + delete-by-POST-flag (`_excluir`) on the same page/template, no separate confirm page.
- **`planos`** — `Plano` (recorrente-por-semana or pacote-de-sessões) and `Contratacao` (a student's active/encerrada/suspensa subscription to a plan). Views mirror the `cadastros` CRUD-on-one-page pattern but not via the shared helper (each is hand-written; keep that in mind if refactoring one).
- **`agenda`** — the scheduling core. See below.
- **`painel`** — the home dashboard (`/`); `alertas.py` computes "upcoming session" notices for the logged-in user's role (professor sees their sessions, aluno sees theirs) for the next 24h.

### The scheduling engine (`apps/agenda/`)

This is the part of the codebase that requires cross-file understanding:

- **`models.py`** — `Sessao` stores three parallel time windows, not just one:
  - `inicio`/`fim`: the actual time the student is with the professor.
  - `reserva_inicio`/`reserva_fim`: the equipment's reserved window (includes `preparo_min` before and `troca_min` after).
  - `prof_inicio`/`prof_fim`: the professor's occupied window — equals `inicio`/`fim` unless the session's `TipoSessao.professor_no_preparo` is set, in which case it equals the equipment window too.
  Also: `EventoSessao` (append-only audit log per session action), `DisponibilidadeProfessor` (weekly availability), `BloqueioEquipamento` (equipment downtime, e.g. maintenance).
- **`motor.py`** — pure rule engine, no side effects. `calcular_janelas(inicio, fim, tipo_sessao)` derives the three window pairs above from a session's real start/end plus its `TipoSessao`'s prep/cleanup minutes. `professor_disponivel` / `equipamento_disponivel` / `verificar_disponibilidade` check for overlapping bookings (and, for equipment, `BloqueioEquipamento` rows) by brute-force scanning that professor's/equipment's non-cancelled sessions — there's no DB-level range query. Change scheduling rules here.
- **`servicos.py`** — the only place that should mutate a `Sessao`: `agendar` / `remarcar` / `cancelar`, each `@transaction.atomic`, each calling into `motor` for conflict checks before writing, and each appending an `EventoSessao`. Views call these instead of touching the model directly. Change what happens on schedule/reschedule/cancel here.
- Views (`views.py`) stay thin: they resolve the requesting user's permissions, build a form, and delegate to `servicos`.

When touching scheduling behavior, the chain to trace is: `TipoSessao` config (prep/cleanup minutes, `professor_no_preparo`) → `motor.calcular_janelas` → `motor.verificar_disponibilidade` → `servicos.agendar`/`remarcar`. Prep/cleanup timing is editable from the Django admin (Tipos de sessão) without code changes.

### Settings & deploy

`config/settings.py` reads all secrets/config from environment variables (via `.env` locally, through `python-dotenv`; real env vars in production — the file explicitly refuses to load `.env` when `VERCEL` or `RENDER` is set). `DATABASE_URL` present → Postgres (via `dj_database_url`, SSL required); absent → local SQLite.

Two deploy targets coexist:
- **Render** (`render.yaml`, `build.sh`): `pip install` → `collectstatic` → `migrate`, then `gunicorn`. Database is Neon Postgres, same AWS region (us-east-1 / Render's `virginia`) to avoid cross-region latency.
- **Vercel** (`pyproject.toml`'s `[tool.vercel.scripts]` → `vercel_build.py`): runs `migrate` + `popular_demo` on every build (so Vercel preview/prod deploys always have demo data seeded).

Static files are served via WhiteNoise (`CompressedManifestStaticFilesStorage`), not a CDN.
