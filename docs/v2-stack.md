# Running the `v2` branch alongside production

`docker-compose.v2.yml` is a fully separate stack: its own project name, ports, Docker images and
Postgres volume. It shares nothing with the stack started from `docker-compose.yml` — both can run on
the same Raspberry Pi at the same time.

```bash
git checkout v2
cp .env.example .env.v2   # edit: can reuse the same GEMINI_API_KEY, use a different SESSION_SECRET
docker compose -f docker-compose.v2.yml --env-file .env.v2 -p poc-control-v2 up -d --build
```

- Web: `http://<host>:${WEB_PORT_V2:-8092}`
- API: `http://<host>:${API_PORT_V2:-8093}`
- Postgres data lives in the `poc-control-v2_pgdata_v2` volume (separate from production's `pgdata`).
- Uploads land in `./uploads_v2/` (separate from production's `./uploads/`).

To stop/remove only this stack without touching production:

```bash
docker compose -f docker-compose.v2.yml --env-file .env.v2 -p poc-control-v2 down
```
