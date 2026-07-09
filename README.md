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
```

`SECRET_KEY` must be private. Generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

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
