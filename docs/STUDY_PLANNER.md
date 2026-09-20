
# Study Planner

## Status

**Planned / Not Implemented.**

The production React shell exposes a `planner` navigation item, but `frontend/src/AppPhase6.jsx` routes it to the generic module-migration placeholder.

No active planner FastAPI route, planner service, planner database table, planner migration or planner-specific API helper was found on the audited branch.

## Do not infer functionality

The current repository does **not** provide verified production implementations for:
- study-task CRUD;
- calendar scheduling;
- deadline planning;
- mastery-to-task scheduling;
- reminders;
- planner persistence;
- Socratic-to-planner writeback.

The Progress Dashboard is a separate implemented subsystem.

## Legacy context

The root Streamlit application contains older study-oriented UI concepts, but those are not connected to the active React/FastAPI planner placeholder.

## Safe future extension point

A future Planner should first define a durable data model and API boundary, then connect the React shell. No schema or API contract should be inferred from the current placeholder.
