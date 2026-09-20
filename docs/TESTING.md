
# Testing

## Current test stack

Backend development dependencies specify `pytest>=8,<9`. Tests are under `backend/tests`.

The repository also contains `.github/workflows/apollo-tests.yml`. This audit inspected the workflow file but did not execute GitHub Actions.

There is no frontend unit/E2E test runner declared in `frontend/package.json`.

## Backend test coverage represented in the tree

The suite contains focused tests for:
- API behavior;
- chat cancellation and partial-response persistence;
- token-aware chunking;
- error classification;
- grounding safeguards;
- history/pagination;
- URL/YouTube ingestion;
- jobs;
- mind maps;
- workspace/session persistence;
- Phase 2 sources;
- Phase 3 Studio;
- Phase 7/production hardening;
- progress/analytics;
- request-body limits;
- retrieval;
- session history;
- Socratic engine;
- Socratic workspace integration;
- source-ingestion security;
- source retry;
- upload safety.

Key files include `test_socratic_engine.py`, `test_socratic_workspace.py`, `test_chat_cancellation.py`, `test_source_ingestion_security.py` and `test_upload_safety.py`.

## Commands

From the backend virtual environment:

~~~powershell
cd backend
pytest
~~~

Frontend static checks/build are declared in `frontend/package.json`:

~~~powershell
cd frontend
npm.cmd run lint
npm.cmd run build
~~~

There is no `npm test` script.

## What is not claimed

This documentation does not claim a verified pass count, coverage percentage or current CI result because this audit did not execute the suite and did not retrieve a complete workflow result.

## Known gaps

No browser E2E framework, dedicated frontend test suite, or repository-integrated security scanner was found in the inspected tree.

## Documentation-only verification

The documentation task itself did not modify application code, dependencies, routes or schemas.
