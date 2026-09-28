# mir-pipeline

A Python backend for ingesting, validating and processing large batches of
precomputed music-feature data, built as a hands-on project to study
backend fundamentals: concurrency, job queues, backpressure and storage design.

Data source: the [AcousticBrainz Genre Dataset](https://mtg.github.io/acousticbrainz-genre-dataset/)
(Essentia-extracted features per recording, plus genre annotations).
Licensed CC BY-NC-SA 4.0, so this project is non-commercial.

## Design decisions

- **Multipart transport, Pydantic validation.** Clients upload files as they
  exist on disk; the server validates each one individually.
- **Loose schema for feature data.** Only the top-level sections and the
  recording ID are validated, not every nested field, so an upstream change in
  the extractor does not break ingestion.
- **Known limit:** Starlette caps a multipart request at 1000 files by
  default, so batch size needs an explicit, documented maximum.

## Current status

- [x] FastAPI `/ingest` endpoint accepting batches via `multipart/form-data`
- [x] Per-file validation with Pydantic; invalid files are rejected with an
      itemized reason while valid ones in the same batch are accepted
- [x] Recording IDs validated as UUIDs before being used as filenames
- [x] Concurrency experiment: naive blocking vs. worker thread vs. process pool
      (results below)
- [x] Process pool for per-file processing
- [ ] Unit and endpoint tests
- [ ] Move processing to a Celery + Redis job queue
- [ ] Bounded queue with HTTP 429 on overload
- [ ] Persist to PostgreSQL (JSONB for feature blobs, promoted columns for
      queryable fields)
- [ ] Docker Compose, Nginx rate limiting
- [ ] Genre taxonomy modelling (evaluate a graph representation)

## Concurrency experiment

Each version was run on the same 900 files (about 11 MB) with `loadtest.sh`,
which uploads one batch while polling `/health` every 0.5 s.
Machine: 8 cores, Fedora Linux, Python 3.14. Warm runs, repeated several times.

| Version | Batch time | Health check during batch |
|---|---|---|
| Blocking, inside `async def` | 6-8 s | stalled about 6 s |
| Worker thread (`asyncio.to_thread`) | 8-9.5 s | 2-10 ms |
| Process pool (`ProcessPoolExecutor`) | 1.8-2.4 s | 2-5 ms |

The first request after startup with the process pool took 3.9 s, and one
health check took 630 ms, which is probably worker start-up cost (not
measured directly).

What this shows:
- Blocking code inside `async def` freezes the whole server, because the
  event loop runs on one thread.
- Threads restore responsiveness but not throughput: the GIL lets only one
  thread run Python code at a time, and hand-off overhead made it slower.
- Processes each have their own GIL, so they give both. The speedup (about
  3-4x on 8 cores) is limited by work that stays serial: parsing the
  upload, pickling data to the workers, collecting results.

## Known limitations

- The process pool runs inside the API server: a restart loses in-flight
  work, nothing bounds how much work can pile up, and the client waits for
  the whole batch. These motivate the job queue (next step).
- Starlette rejects multipart requests with more than 1000 files, so a
  maximum batch size needs to be defined and documented.
- Two files with the same recording ID in one batch would be written
  concurrently to the same path. This does not occur in this dataset, but
  duplicates need an explicit policy.
- Benchmarks are from one machine and one folder of the dataset (5,763 files).

## Run locally

    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    uvicorn main:app --reload
    ./loadtest.sh /path/to/folder/of/json/files 900
