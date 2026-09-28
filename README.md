# mir-pipeline

A Python backend for ingesting, validating and processing large batches of
precomputed music-feature data, built as a hands-on project to study
backend fundamentals: concurrency, job queues, backpressure and storage design.

Data source: the [AcousticBrainz Genre Dataset](https://mtg.github.io/acousticbrainz-genre-dataset/)
(Essentia-extracted features per recording, plus genre annotations).
Licensed CC BY-NC-SA 4.0, so this project is non-commercial.

## Current status

- [x] FastAPI `/ingest` endpoint accepting batches via `multipart/form-data`
- [x] Per-file validation with Pydantic; invalid files are rejected with an
      itemized reason while valid ones in the same batch are accepted
- [x] Recording IDs validated as UUIDs before being used as filenames
- [x] Measured the naive synchronous version under load: a 900-file batch
      blocks the event loop for about 6.5 s, and a health check sent mid-batch
      took 6 s instead of about 2 ms
- [ ] Move processing to a Celery + Redis job queue
- [ ] Bounded queue with HTTP 429 on overload
- [ ] Persist to PostgreSQL (JSONB for feature blobs, promoted columns for
      queryable fields)
- [ ] Tests, Docker Compose, Nginx rate limiting
- [ ] Genre taxonomy modelling (evaluate a graph representation)

## Design decisions

- **Multipart transport, Pydantic validation.** Clients upload files as they
  exist on disk; the server validates each one individually.
- **Loose schema for feature data.** Only the top-level sections and the
  recording ID are validated, not every nested field, so an upstream change in
  the extractor does not break ingestion.
- **Known limit:** Starlette caps a multipart request at 1000 files by
  default, so batch size needs an explicit, documented maximum.

## Run locally

    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    uvicorn main:app --reload
