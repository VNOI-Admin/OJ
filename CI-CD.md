# CI/CD cho ThinkCode OJ

Toan bo logic CI/CD nam trong GitHub Actions:

```text
.github/workflows/ci.yml
.github/workflows/cd.yml
```

Server khong giu `deploy.sh`, SSH wrapper, source code, private key, `.env`,
`local_settings.py` hoac file compose co dinh.

## Flow

`ci.yml` chay tren push va pull request:

```text
lint: flake8 + Python syntax
test: Django checks + unit tests
styles: build stylesheet
```

Khi CI tren branch `deploy` thanh cong, `cd.yml` se:

```text
checkout dung commit da test
build Docker image
push image len GHCR
SSH vao server
truyen GitHub Secrets qua stdin
docker login GHCR
pull image
check --deploy bang production env
migrate database
sync static assets
docker compose down
docker compose up -d
xoa config tam tren server
```

## GitHub Secrets

Tao GitHub Environment ten `production` va cac secrets:

| Secret | Noi dung |
|---|---|
| `DEPLOY_HOST` | IP hoac hostname production |
| `DEPLOY_USER` | User SSH co quyen chay Docker |
| `DEPLOY_SSH_KEY` | Private SSH key danh rieng cho CD |
| `PRODUCTION_ENV` | Toan bo noi dung file env production |

`GITHUB_TOKEN` duoc GitHub cap tu dong de push image va login GHCR.

`PRODUCTION_ENV` la multiline secret, vi du:

```dotenv
DJANGO_SECRET_KEY=...
DJANGO_DEBUG=False
ALLOWED_HOSTS=oj.thinkcode.vn
CSRF_TRUSTED_ORIGINS=https://oj.thinkcode.vn
DB_NAME=dmoj
DB_USER=dmoj
DB_PASSWORD=...
DB_HOST=127.0.0.1
DB_PORT=3306
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/0
```

Khong dua secret production vao Dockerfile, source code hoac image layer.

## Production Image

`dmoj/local_settings.docker.py.example` khong chua secret va duoc copy vao
image voi ten `dmoj/local_settings.py` khi build.

File nay doc cau hinh tu environment runtime. CD truyen `PRODUCTION_ENV` vao
cac container bang `--env-file` hoac Compose.

## Server Setup

Server chi can:

- Docker Engine
- Docker Compose plugin
- User deploy thuoc group `docker`
- Public SSH key tuong ung voi `DEPLOY_SSH_KEY`
- Cac thu muc du lieu persistent:
  - `/var/www/thinkcodeoj/media`
  - `/var/www/thinkcodeoj/problem_data`
  - `/var/www/thinkcodeoj/static`
  - `/var/log/thinkcodeoj`

Public key trong `~/.ssh/authorized_keys` nen gioi han forwarding:

```text
no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... github-actions-cd
```

Private key chi ton tai trong GitHub Secret. Workflow tao file key tam tren
runner va xoa file nay sau deploy.

## R2 Storage

R2 credentials are runtime-only. Do not put them in the Dockerfile, image,
repository, or a persistent server compose file. The application reads the
following variables from `PRODUCTION_ENV` when `USE_R2_MEDIA=True`:

```dotenv
USE_R2_MEDIA=False
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_MEDIA_BUCKET=thinkcode-media
R2_MEDIA_CUSTOM_DOMAIN=media.oj.thinkcode.vn
R2_MEDIA_PRIVATE=False
R2_PROBLEMS_BUCKET=thinkcode-problems
```

MariaDB backups use a separate, backup-only R2 credential and the
`deploy/thinkcode-r2-backup.service` and `.timer` templates. The live database
remains on MariaDB; the backup job only runs `mariadb-dump --single-transaction`
and uploads a compressed copy.

Problem releases use `python manage.py publish_problem_release CODE VERSION`.
Judges use `scripts/sync_problem_release.py` with a read-only problems-bucket
credential. R2 is never mounted as the judge filesystem.

Rollback for media is `USE_R2_MEDIA=False` followed by a normal CD deployment.
The judge rollback is to keep the last verified local `/problems/<code>` tree;
the sync script refuses checksum failures before replacing it.

## Runtime Config Tam

Moi lan deploy, `cd.yml`:

1. Ma hoa noi dung `PRODUCTION_ENV` va `docker-compose.production.yml` bang base64 de truyen qua stdin.
2. Ghi chung vao `/tmp/thinkcode-deploy` tren server.
3. Chay validation, migration va Compose.
4. Xoa thu muc tam bang shell trap khi ket thuc.

Khong co file cau hinh deploy nao duoc giu lai sau workflow. Container van giu
environment runtime da duoc Docker nap khi khoi dong.

## Downtime Va Rollback

CD dung flow don gian:

```bash
docker compose down --remove-orphans
```

Vi vay co downtime ngan trong luc bon service `site`, `bridged`, `celery`,
`wsevent` duoc thay the. MariaDB, Redis va nginx native khong bi dung.

Phase nay chua co rollback tu dong. Image tag theo commit cho phep rollback
thu cong bang cach chay lai CD voi commit cu.
