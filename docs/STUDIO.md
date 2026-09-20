
# Studio

## Current capabilities

The active Phase 3 Studio supports:

- slides;
- report;
- podcast;
- source transformations;
- video storyboard.

The mind-map endpoint is implemented separately and shares the same source-grounding stack.

## Generation flow

~~~mermaid
flowchart TD
  UI[StudioPanel] --> A[frontend/src/api/studioApi.js]
  A --> R[/studio/generate or /studio/slides]
  R --> C[context_builder]
  C --> G[Gemini]
  G --> V[JSON/content validation]
  V --> I[(apollo_source_insights)]
  I --> UI
~~~

## Slides

The Phase 3 Studio can generate structured slide data. The older direct `/api/notebooks/{notebook_id}/studio/slides` route in `main.py` can build a real PPTX through `pptx_generator.build_source_grounded_pptx`.

Treat both as current backend capabilities, but note that the React Studio drawer uses the Phase 3 `studioApi.js` flow.

## Report

The report tool returns structured report data plus Markdown. The backend compares report text against source context. When the overlap is low, it can perform one stricter regeneration attempt and returns verification metadata.

## Podcast

Podcast generation returns a two-speaker HOST/EXPERT script, persisted as a notebook insight. It is a script generator, not an audio-rendering service in the current Phase 3 route.

## Transformations

`backend/transformations.py` provides:
`summary`, `key_points`, `key_concepts`, `faq`, `outline`, `glossary`, `quiz`, `study_guide`, `flashcards`, `timeline`, `compare_contrast`, `explain_simply` and `misconceptions`.

The Phase 3 route also supports a `custom` transformation prompt.

## Video

**Partially Implemented.** The active Phase 3 `video` tool returns storyboard JSON with title, duration and scene objects. It does not render or persist a video file. The frontend copy also describes storyboard support.

The root `video_generator.py` is legacy/non-production and must not be used as evidence that production video generation exists.

## Mind map / diagram

`/api/notebooks/{notebook_id}/mindmap` generates source-grounded diagram content, renders it to SVG, measures overlap against the supplied context and can retry once with stricter grounding instructions.

## Persistence

Studio results are persisted as `apollo_source_insights` when the Postgres store is active. The insight record keeps tool-specific `insight_type` and `model_used` metadata.

## Failure boundaries

Studio requires indexed source content for the selected notebook. Typical failures:
- 400 — missing notebook/source context or invalid transformation;
- 502/503 — provider or structured-output failure;
- 504 — request timeout.

The implementation uses bounded Gemini fallback and request timeouts rather than an external generation queue.
