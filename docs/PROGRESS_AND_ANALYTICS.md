
# Progress and Analytics

## Current implementation

The current frontend page is `frontend/src/ProgressDashboardPage.jsx`. It calls `GET /api/progress/dashboard`, implemented by `backend/analytics_service.py`.

The dashboard exposes:

- current and longest streak;
- active study days;
- total sessions;
- Socratic sessions;
- total and assistant message counts;
- message activity calendar;
- mastery attempts and correct answers;
- mastery accuracy;
- average mastery score;
- proficient topics (score ≥ 75);
- mastered topics (score ≥ 90).

## Data sources

On Postgres, analytics derive directly from `apollo_chat_sessions`, `apollo_chat_messages` and `apollo_socratic_mastery`.

The service does not create a separate analytics warehouse or event stream.

Filesystem fallback reconstructs equivalent activity from workspace JSON and the Socratic mastery JSON.

## Socratic relationship

The integration is real but narrow:

- Socratic sessions can be counted from session state;
- mastery statistics come from the durable mastery aggregate.

The dashboard does not derive mastery from semantic analysis of every Socratic message.

## UI behavior

The current UI offers 7, 30 and 90-day windows. Backend validation supports a broader 7–365 day range.

## Planner boundary

There is no study-task planner or scheduling model in analytics. Do not infer planner functionality from the dashboard's learning telemetry.

## Testing

The repository has `backend/tests/test_progress_analytics.py` for the analytics behavior.

## Known limitations

No dedicated event/telemetry database, spaced-repetition schedule or calendar integration is present in the current production schema.
