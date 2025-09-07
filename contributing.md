# Contributing to VNOJ

## Issues found

First check if the bug is reported or not under [Issues](https://github.com/VNOI-Admin/OJ/issues)

If you're unable to find an open issue addressing the problem, [open](https://github.com/VNOI-Admin/OJ/issues/new) a new one. Be sure to include a title and clear description, as much relevant information as possible, and a code sample or an executable test case demonstrating the expected behavior that is not occurring.

## Submitting changes

Ensure the PR description clearly describes the problem and solution. Include the relevant issue number if applicable.

## Developer Quickstart

This quickstart is intended for contributors who want to run VNOJ locally in **development mode**.  
It is a simplified flow compared to the full production installation guide in [vnoj-docs](https://vnoi-admin.github.io/vnoj-docs/).

### Requirements
- **Python** ≥ 3.9 (with `venv` and `pip`), you can use `uv` or `pyenv`.
- **Node.js** ≥ 18.x + npm/pnpm
- **MariaDB/MySQL** ≥ 10.6 
- **Redis** ≥ 6 (running on port 6379)
- **Git**
- A small cup of coffee.

Any Linux distribution or macOS should work. On Windows, WSL2 with Ubuntu/Debian is recommended.

### 1. Clone & create virtual environment
```bash
pip install uv && npm install -g pnpm
uv venv vnojsite
source vnojsite/bin/activate

git clone https://github.com/VNOI-Admin/OJ.git site
cd site

uv pip install -r requirements.txt
pnpm install
````

### 2. Database setup

Create a database and user (replace `<mariadb user password>` with your own):

```sql
CREATE DATABASE dmoj DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_general_ci;
GRANT ALL PRIVILEGES ON dmoj.* TO 'dmoj'@'localhost' IDENTIFIED BY '<mariadb user password>';
```

### 3. Local configuration

```bash
cp dmoj/local_settings.py.example dmoj/local_settings.py
```

- Update DB credentials in `local_settings.py`.
- Keep `DEBUG = True` for development.

### 4. Migrate & load demo data

```bash
python manage.py migrate
python manage.py loaddata navbar language_small demo
```

### 5. Create superuser & run server

```bash
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

Access `http://127.0.0.1:8000` and log in with your admin account.

### 6. Optional: run background services

```bash
python manage.py runbridged    # event bridge
celery -A dmoj_celery worker   # Celery tasks
```

### 7. Optional: Compiling assets

```bash
./make_style.sh
python manage.py collectstatic
python manage.py compilemessages
python manage.py compilejsi18n
```

---

⚡ This setup is enough to:

* Explore the site locally
* Test templates, UI, and most features
* Make contributions without a full production deployment

## Coding convention

We use flake8.

## Translation
Vietnamese translation is stored in [this folder](locale/vi/LC_MESSAGES). Feel free to do a PR on this file.