# Studio Fitness — Agenda e Gestão

Plataforma web (responsiva, sem app nativo) para o Studio Fitness: agenda que cruza **professor + equipamento de eletroestimulação + aluno**, respeitando os tempos de preparo e troca.

Fase atual: **Fase 1 / Pacote Básico**. Planejamento completo em [docs/PLANO.md](docs/PLANO.md).

## Rodando localmente

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # DEBUG=True, SQLite
python manage.py migrate
python manage.py popular_demo     # dados de demonstração
python manage.py runserver
```

Logins de demonstração (senha `demo1234`): `gestor`, `bia`, `leo`, `felipe` (professores) e `mariana` (aluna).

- App: http://127.0.0.1:8000
- Cadastros (gestor): http://127.0.0.1:8000/admin/

## Testes

```bash
python manage.py test
```

## Onde mexer

| Quero… | Arquivo |
|---|---|
| Mudar uma regra de agenda | `apps/agenda/motor.py` |
| Mudar o que acontece ao agendar/remarcar/cancelar | `apps/agenda/servicos.py` |
| Mudar os alertas da home | `apps/painel/alertas.py` |
| Ajustar tempos de preparo/troca | Admin → Tipos de sessão (não precisa mexer em código) |

## Deploy

Render (Web Service) + Neon (Postgres), ambos em us-east-1. Veja a seção 9 do [plano](docs/PLANO.md#9-deploy-e-ambientes).
# studio-fitness
