# YChat 2.0

A modern Flask chat application foundation with registration, secure login, password hashing, SQLite persistence, and a responsive UI.

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open the local Flask URL shown in the terminal in your browser.

## Environment Variables

Development uses SQLite at `instance/ychat.sqlite3` automatically.

For production, set:

```text
APP_ENV=production
SECRET_KEY=<strong-random-secret>
DATABASE_URL=<render-postgres-url>
REDIS_URL=<redis-connection-url>
```

`SECRET_KEY` must be private. Generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Private uploads are stored under `instance/uploads` by default and are served only through authenticated application routes. For production, mount a private persistent volume and set `UPLOAD_FOLDER` to that path.

## Security verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
$env:APP_ENV="development"; .\.venv\Scripts\python.exe app.py
```

See `SECURITY_CHECKLIST.md` before production deployment. Production requires a reachable Redis service for shared rate limits. Development uses Redis when `REDIS_URL` is reachable and otherwise logs a warning and falls back to memory.

## Importing legacy JSON messages

The import is idempotent and writes `.bak` files beside every JSON source before importing:

```powershell
$env:FLASK_APP="app.py"
.\.venv\Scripts\flask.exe import-json-messages
# After verifying message counts and history:
.\.venv\Scripts\flask.exe import-json-messages --delete-originals
```

The second form deletes an original only after its backup exists. Keep the backups until database backups have been verified.

## Deploying On Render

This project includes `render.yaml` for Render Blueprint deployment.

1. Commit the deployment files:

```powershell
git add .
git commit -m "Prepare Render deployment"
```

2. Push the repository to GitHub:

```powershell
git push
```

3. Open Render and choose **New +** then **Blueprint**.
4. Connect your GitHub account if Render asks.
5. Select this repository.
6. Confirm the blueprint settings from `render.yaml`.
7. Render will create:
   - a Python web service
   - a PostgreSQL database
   - production environment variables
8. Click **Apply** or **Deploy**.
9. Open the generated Render service URL after the deploy finishes.

Render will run:

```bash
pip install -r requirements.txt
gunicorn -c gunicorn.conf.py app:app
```

SQLite is only used for local development. Production uses Render PostgreSQL through `DATABASE_URL`, so the app keeps running on Render even when your computer is off.
