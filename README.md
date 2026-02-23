# KPIAYA — Production-ready KPI Management Platform

FastAPI + PostgreSQL + SQLAlchemy (async) platform for enterprise KPI lifecycle with Telegram-only auth, RBAC, auditing, disputes, sharing, export, and scheduler reminders.

## Core capabilities
- Telegram auth via `initData` HMAC verification (official algorithm).
- JWT access + refresh tokens.
- RBAC with extensible `roles`, `permissions`, `user_roles`, `role_permissions`.
- Immutable always-existing super admin:
  - `username=Joshua_Eng1`
  - `telegram_id=6707954035`
- KPI templates with DB-stored formulas and weights (no hardcoded math).
- KPI instances with periods, archive rules, immutable approved KPIs.
- KPI share links (Google Docs style): anonymous read + optional download.
- Full audit history (`kpi_history`) of business actions.
- PDF/Excel export for admin and sharing flows, including batch ZIP export.
- User directory API with filters, pagination, sorting, CSV export.
- KPI disputes with Telegram notifications.
- APScheduler persistent monthly reminders (20/22/23).

## Quick start
```bash
cp .env.example .env
# set SECRET_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_WEBAPP_SECRET
docker-compose up --build
```

Open:
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Security model
1. Telegram-only authentication (`/api/v1/auth/telegram`).
2. Telegram signature validation using HMAC-SHA256 over `initData`.
3. Whitelist enforced by `User.whitelist_enabled` (except immutable super admin).
4. Role/permission checks through dependency middleware.
5. Audit trails in `kpi_history` for writes and share link openings.
6. All sensitive parameters are env-driven.

## KPI formula engine
Formulas are stored in `kpi_template_metrics.formula` and evaluated against context variables:
- `max_total_amount`
- `weight_percent`
- `plan_value`
- `fact_value`
- `max_metric_amount`

Default formula example:
```python
max_metric_amount * (fact_value / plan_value)
```

## ER Diagram (text)
- `users` 1..* ↔ *..1 `roles` via `user_roles`.
- `roles` 1..* ↔ *..1 `permissions` via `role_permissions`.
- `kpi_templates` 1..* `kpi_template_metrics`.
- `kpi_instances` references `users` + `kpi_templates` and has * `kpi_instance_metrics`.
- `kpi_disputes` references `kpi_instances`, optional `kpi_instance_metrics`, and creator user.
- `kpi_history` stores immutable change snapshots.
- `kpi_share_links` stores anonymous-access links with scope/permission/expiry.
- `notification_logs` stores outbound Telegram sends/reminders.

## Key endpoints
- `POST /api/v1/auth/telegram`
- `POST /api/v1/kpi/instances`
- `POST /api/v1/kpi/disputes`
- `POST /api/v1/kpi/share-links`
- `GET /api/v1/kpi/share/{uuid}`
- `GET /api/v1/kpi/export/{instance_id}?fmt=pdf|xlsx`
- `GET /api/v1/users`
- `GET /api/v1/users/export/csv`

## Notes
- Super admin bootstrap runs on startup and is enforced each launch.
- Approved/archive protection should be expanded with dedicated policy checks if you add write endpoints.
- For true HA scheduler persistence, back APScheduler with Redis/SQL job store in production.
