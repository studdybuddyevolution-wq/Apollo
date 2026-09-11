# Apollo free deployment

Apollo is split into two services:

- `frontend/` — React + Vite, deployed to Cloudflare Pages.
- `backend/` — FastAPI, deployed to Render Free.

Cloudflare Pages builds the frontend with `npm run build` and publishes `dist`. Render runs the FastAPI service with Uvicorn on Render's `$PORT`.

## 1. Push/pull the latest repo

```cmd
git pull origin main
```

## 2. Local environment

Copy `.env.example` to `.env` in the repository root and set:

```env
GROQ_API_KEY=gsk_...
APOLLO_CORS_ORIGINS=http://localhost:5173
```

Never commit `.env`.

For local frontend development, `frontend/.env.example` can be copied to `frontend/.env` if needed, but it may remain empty because Vite proxies `/api` to `http://127.0.0.1:8000` during development.

## 3. Render backend

Use the repository's `render.yaml` Blueprint, or create a Web Service manually with:

- Root Directory: `backend`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/api/health`
- Plan: Free

Set these Render environment variables in the service:

- `GROQ_API_KEY` = your Groq API key
- `APOLLO_CORS_ORIGINS` = your Cloudflare Pages production URL, for example `https://apollo.pages.dev`

After deployment, verify:

```text
https://YOUR-RENDER-SERVICE.onrender.com/api/health
```

The response should include `"groq_configured":true`.

## 4. Cloudflare Pages frontend

Create a Pages project from the GitHub repository and configure:

- Production branch: `main`
- Root directory: `frontend`
- Build command: `npm run build`
- Build output directory: `dist`

Add this Cloudflare Pages environment variable for the production build:

```text
VITE_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com
```

This value is intentionally a Vite build-time variable. Do not put API secrets in `VITE_*` variables because they are exposed to browser code.

## 5. Connect CORS after Cloudflare deployment

Once Cloudflare gives you the final Pages URL, set the Render variable:

```text
APOLLO_CORS_ORIGINS=https://YOUR-PAGES-PROJECT.pages.dev
```

Redeploy/restart the Render service after changing it.

## 6. Local run

Backend:

```cmd
cd backend
uvicorn main:app --reload --port 8000
```

Frontend:

```cmd
cd frontend
npm.cmd run dev
```

Open `http://localhost:5173`.
