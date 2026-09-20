
# Changelog — Architecture Milestones

This is a curated architectural history, not a full commit log.

## Durable PostgreSQL persistence

**Representative commits:** `8dc886364bd391a3310a13fc7fd697f3ded65b4a`, `62aa655a82967dfa06d5d92a74cafcfc8b1f52f6`, `baeb48ed1e6c93fa0e626d6a5675e304b1521601`, `cbe2634c17711f40aa0ab590082fc530b5765a6f`.

The project moved notebook/chunk persistence to Postgres when configured, extended that durable path to sources/payloads/sessions/notes/insights/jobs, exposed durability in health metadata, and clarified that filesystem storage is development-only for production deployment.

## Source lifecycle and hardening

During the 15–18 September 2026 hardening period, the repository added source status/error tracking, refreshable source URLs, raw source payload persistence, safe unique names, upload/request limits and retry classification.

## Deep Research evolution

**Representative commits:** `7ba2afbcb64245163fc215e701491633c08e6988`, `0c7e59158ca9bc96d5308fd192d6048e032f1169`, `f4472ebd5a8fe42752980d9cb596de46fb1d4720`, `01d61ba8fcd5189f526f916d019d1bcd2385d6e7`, `65eabefd01c0a445df95fa0922d961731d0922fd`, `fa620392f021133e08d5e865a68c9e19b4b7dbc1`.

The research engine evolved through hybrid retrieval, parallel passes, adaptive sections, explicit user headings and a post-stream grounding check.

## Cancellation hardening

**Representative commits:** `e4093cb0883f3663d9a6c1039d03ca2881c219f8`, `fb3051acfa6ce871170f5d35461eb56e5adad454`, `b6bd3b56b64549728aff1134e614509bf00bbe57`, `32d3e29dc3a5fc90e349e888884a647f04d373de`.

The workspace stream was hardened so a partially generated assistant response is persisted when the client stops/cancels.

## Studio/video clarification

A production-hardening commit explicitly clarified that Video Overview is storyboard output rather than video rendering. The Phase 3 backend now returns a storyboard structure and the active UI describes it accordingly.

## Socratic Tutor

The audited branch contains the Marklyf-native phase state machine, shared workspace transport, durable session state, Quick Check/mastery endpoints and frontend phase UI.

The repository's keyword commit search did not expose a stable Socratic-specific commit sequence, so this document does not invent commit IDs or dates for individual Tutor steps. The implementation evidence does show that Socratic behavior is layered onto the already-existing workspace/session/RAG architecture.

## Current production composition

**Current branch tip audited:** `phase8/production-hardening` at `87558a1d9d9ef34429cadf9de51020d0c18d63c5`.

A rebrand commit changed active user-facing copy from Apollo to Marklyf while preserving technical compatibility identifiers. The production architecture remains React/Vite + FastAPI + Postgres when configured.

## Legacy systems

Root Streamlit/UI modules remain in the repository, including older tutor/video/studio behavior. They are historical/legacy and are not the Cloudflare + Render production runtime.
