# Running POC Control from the published images

Source: [github.com/FlavioFGM/suse-poc-toolkit/poc-control](https://github.com/FlavioFGM/suse-poc-toolkit/tree/main/poc-control) — this file
covers running it from the prebuilt images on Docker Hub, without cloning or building anything.

POC Control is a personal tool for a Solutions Architect to run customer proofs-of-concept:
extract a test plan from a PDF/Word/spreadsheet, get an AI-assisted first pass at which items
are supported (with web-sourced evidence), track execution session by session, and export a
client-ready report.

## Images

- `gabriellins/poc-control:api` — FastAPI backend (Python)
- `gabriellins/poc-control:web` — React frontend, served by nginx (also proxies `/api`)

**ARM64 only.** Both images are built on a Raspberry Pi (the project's own ARM64 deployment
target) — there's no multi-platform manifest yet, so they won't run on an amd64 host without
emulation (`--platform linux/arm64` under QEMU works, but slowly).

You also need a **PostgreSQL + [pgvector](https://github.com/pgvector/pgvector) 16** database —
not published here, pull `pgvector/pgvector:pg16` directly (it already has an ARM64 build).

## 1. `docker-compose.yml`

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  api:
    image: gabriellins/poc-control:api
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      ADMIN_EMAIL: ${ADMIN_EMAIL}
      ADMIN_PASSWORD_HASH: ${ADMIN_PASSWORD_HASH}
      SESSION_SECRET: ${SESSION_SECRET}
      GEMINI_API_KEY: ${GEMINI_API_KEY}
    volumes:
      # :Z relabels these for the container's SELinux context -- needed on SELinux-enforcing
      # hosts (e.g. SLES), otherwise the api container gets a plain PermissionError writing
      # under uploads/ even running as root. Harmless no-op on hosts without SELinux.
      - ./seed:/app/seed:ro,Z
      - ./uploads:/app/uploads:Z
    depends_on:
      db:
        condition: service_healthy
    ports:
      - "${API_PORT:-8091}:8000"
    restart: unless-stopped

  web:
    image: gabriellins/poc-control:web
    depends_on:
      - api
    ports:
      - "${WEB_PORT:-8090}:80"
    restart: unless-stopped

volumes:
  pgdata:
```

Create empty `seed/` and `uploads/` folders next to it (Docker will create them anyway on first
run if they're missing, but having them ready avoids a root-owned auto-created directory).

## 2. `.env`

```dotenv
POSTGRES_USER=poc_control
POSTGRES_PASSWORD=changeme
POSTGRES_DB=poc_control

ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD_HASH=

SESSION_SECRET=changeme

GEMINI_API_KEY=

WEB_PORT=8090
API_PORT=8091
```

- `GEMINI_API_KEY`: a [Gemini API](https://aistudio.google.com/) key — required for every
  AI-assisted feature (item extraction, classification, RFI analysis, summaries).
- `SESSION_SECRET`: any random string, e.g. `openssl rand -hex 32`.
- `ADMIN_PASSWORD_HASH`: see step 3 below — **read it before filling this in**, there's a
  Docker Compose gotcha with the `$` characters an argon2 hash contains.

## 3. Create the admin login

The app seeds a single user from `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` on first startup. Generate
the hash straight from the image you already pulled — no need to install Python or argon2
locally:

```sh
docker run --rm gabriellins/poc-control:api python scripts/hash_password.py "your-password"
```

That prints an argon2 hash shaped like `$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`.

**Docker Compose reads `$` in `.env` as a variable reference** (`$argon2id` looks like a
variable called `argon2id`) and silently blanks it out — the container ends up with a corrupted
hash and login fails with no obvious error. Escape every `$` as `$$` before pasting it into
`.env`:

```dotenv
ADMIN_PASSWORD_HASH=$$argon2id$$v=19$$m=65536,t=3,p=4$$<salt>$$<hash>
```

**This `$$` escaping is a real-Docker-Compose-only quirk.** `podman-compose` (used on e.g. a SLES
deployment) does **not** interpolate `.env` values at all — doubling the `$` there leaves a
literal `$$` in the container's environment, which is just as broken as the unescaped version,
for the opposite reason. On podman-compose, paste the hash exactly as `hash_password.py` printed
it, single `$` and all. Whichever engine you're on, verify once with:

```sh
podman exec <api-container> printenv ADMIN_PASSWORD_HASH   # or: docker compose exec api printenv ADMIN_PASSWORD_HASH
```

and confirm it matches the hash you generated, before assuming login will work.

## 4. Run it

```sh
docker compose up -d
```

Migrations and the admin-user seed run automatically on the `api` container's startup — nothing
else to run by hand. Open `http://<host>:8090` and log in with `ADMIN_EMAIL` and the plaintext
password you hashed in step 3.

## 5. Load the sample procedures (optional)

A new install has no procedures. Three validated ones ship in `seed/procedimentos/` (Argo CD to k3s, HPA with
Ingress, Vault integration). They are **not** loaded automatically: log in once, save your Gemini key under
*My account*, then run

```sh
docker compose exec api python scripts/import_seed.py --user you@example.com
```

`--user` is your login's e-mail: you become the owner of the procedures and the Gemini key from *My account* is
the one used for the embeddings and the English translation. Without `--user` the script uses `GEMINI_API_KEY`
from the environment and the procedures have no owner. It goes through the same code as a web upload, skips
procedures that already exist, and is safe to run again. The samples are written in Portuguese; they are
translated on demand to the language of the screen.

## Updating

```sh
docker compose pull
docker compose up -d
```

## Full documentation

The [GitHub repo](https://github.com/FlavioFGM/suse-poc-toolkit/tree/main/poc-control) has the full feature list, data model,
and architecture notes (`README.md`), and the day-to-day engineering/product context
(`CLAUDE.md`).
