
# Frontend

## Stack and entrypoint

The production UI is React with Vite. `frontend/src/main.jsx` renders `AppPhase6` inside `React.StrictMode`. Vite is configured in `frontend/vite.config.js`; its development server proxies `/api` to `http://127.0.0.1:8000`.

Cloudflare deployment uses `frontend/src/worker.js` and the assets in `dist`. The Worker prevents browser/CDN caching of SPA HTML while allowing hashed JS/CSS to remain cacheable.

## Main application component

`frontend/src/AppPhase6.jsx` contains the current application shell and most feature UI. Important internal components are:

| Component | Responsibility |
|---|---|
| `Sidebar` | Notebook selection/navigation |
| `TopBar` | Research mode + Sources/Studio/Sessions/Notes controls |
| `Composer` | Chat input, send, stop/cancel |
| `SourcePanel` | Upload, URL/YouTube import, source modes |
| `SessionPanel` | Current notebook sessions |
| `PastSessionsPage` | Search/filter/paginated session history |
| `SocraticTutor` | Socratic phase UI, Move Forward, Quick Check |
| `StudioPanel` | Studio tool selection and generation |
| `ProgressDashboardPage` | Learning telemetry |
| `NotesPanel` | Persisted notes |

The application uses React hooks and local state rather than a separate global state library.

## API abstraction

- `frontend/src/api/apolloApi.js` owns streaming chat, health, diagrams/jobs and Socratic-specific helpers.
- `frontend/src/api/notebooksApi.js` owns notebooks, sources, sessions, notes and progress.
- `frontend/src/api/sourceIngestionApi.js` owns URL/YouTube source import.
- `frontend/src/api/studioApi.js` owns Studio and mind-map calls.

All helpers normalize backend errors from `detail` and use `VITE_API_BASE_URL` when configured. The API helper's default backend URL is the current public Render service.

## Identity and local UI state

The browser creates `apollo-user-id` in localStorage on first use. Recent notebooks, recent sources and per-notebook source modes are also stored in localStorage. This is convenience state/data scoping, not authentication.

## Streaming and cancellation

`streamChat()` starts a POST request with an `AbortController.signal`, then reads SSE frames from the response body. Recognized event types include `session`, `start`, `fallback`, `restart`, `grounding_check`, `socratic_state`, `token`, `sources` and `done`.

The chat UI inserts an assistant placeholder immediately, appends streamed text as tokens arrive, and changes the message text on abort/error. The stop action calls the controller's abort path.

## Source selection

Source modes are `full`, `summary`, `insights` and `off`. The active source list is derived from sources whose mode is not `off`. The chosen mode map is persisted locally per user/notebook and forwarded to backend context construction.

## Socratic UI

The Socratic page displays the current phase/status, progress, mastery score/tier, message history, Quick Check state and Move Forward action. It uses the same `send()`/streaming path as normal workspace chat with `research_mode="socratic"`.

## Research and Studio

Research mode selection is a five-value UI: quick, socratic, web, deep and study. Studio exposes slides, report, mindmap, transform, podcast and video. The video UI is explicitly storyboard-only.

## Progress and planner

Progress uses `ProgressDashboardPage.jsx` and calls `/api/progress/dashboard`. The Planner nav item exists but resolves to the generic migration placeholder; there is no active planner component/API.

Settings/Profile likewise resolves to the placeholder. Treat both as **Planned / Not Implemented**.

## Browser navigation

There is no React Router dependency in `frontend/package.json`. Navigation is state-driven inside `AppPhase6.jsx`; “pages” are selected by the `active` state value.

## Legacy frontend

The root Streamlit application and Python UI modules are not imported by `frontend/src/main.jsx`. They are legacy/non-production for this deployment.
