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
  default. The API enforces its own lower limit (500) and returns HTTP 429
  above it, rather than relying on the framework's cap.
- **Job completion is detected via `HINCRBY`'s return value**, not a
  separate read-then-compare. Redis guarantees each call returns a unique,
  strictly increasing count, so exactly one task can ever observe "this was
  the last file," with no race between two tasks both thinking they finished
  the batch.
- **Results are only deleted from Redis after a successful disk write.** If
  writing the results file fails, the raw results stay in Redis and the job
  status becomes `completed_with_errors` instead of silently losing data.

## Current status

- [x] FastAPI `/ingest` endpoint accepting batches via `multipart/form-data`
- [x] Per-file validation with Pydantic; invalid files are rejected with an
      itemized reason while valid ones in the same batch are accepted
- [x] Recording IDs validated as UUIDs before being used as filenames
- [x] Concurrency experiment: naive blocking vs. worker thread vs. process pool
      (results below)
- [x] Unit tests for per-file processing and Celery task dispatch
- [x] Celery + Redis job queue: `/ingest` returns a `batch_id` immediately;
      processing happens in background workers
- [x] Bounded batch size with HTTP 429 on overload (limit: 500 files)
- [x] `GET /jobs/{batch_id}` status endpoint and `GET /jobs/{batch_id}/results`
- [ ] Persist job records to PostgreSQL (currently Redis for live status,
      a JSON file for the final results — see Known limitations)
- [ ] Persist feature data to PostgreSQL (JSONB for feature blobs, promoted
      columns for queryable fields)
- [ ] Docker Compose, Nginx rate limiting
- [ ] Genre taxonomy modelling (evaluate a graph representation)
- [ ] Bulk Celery dispatch, to reduce per-batch Redis round-trips (see below)

## Concurrency experiment (pre-queue)

Before the job queue existed, three versions of synchronous-style processing
were compared, each run on the same 900 files (about 11 MB) with
`loadtest.sh`, which uploads one batch while polling `/health` every 0.5 s.
Machine: 8 cores, Fedora Linux, Python 3.14. Warm runs, repeated several times.

| Version | Batch time | Health check during batch |
|---|---|---|
| Blocking, inside `async def` | 6-8 s | stalled about 6 s |
| Worker thread (`asyncio.to_thread`) | 8-9.5 s | 2-10 ms |
| Process pool (`ProcessPoolExecutor`) | 1.8-2.4 s | 2-5 ms |

The first request after startup with the process pool took 3.9 s, and one
health check took 630 ms, probably worker start-up cost (not measured
directly).

What this shows:
- Blocking code inside `async def` freezes the whole server, because the
  event loop runs on one thread.
- Threads restore responsiveness but not throughput: the GIL lets only one
  thread run Python code at a time, and hand-off overhead made it slower.
- Processes each have their own GIL, so they give both. The speedup (about
  3-4x on 8 cores) is limited by work that stays serial: parsing the
  upload, pickling data to the workers, collecting results.

This process pool version has since been replaced by the job queue below,
which solves the three limitations the process pool still had: work lost on
restart, no bound on queued work, and the client waiting for the whole batch.

## Job queue (Celery + Redis)

Submitting a batch now returns a `batch_id` immediately; actual file
processing happens in background Celery workers. Status and results are
retrieved via separate polling endpoints.

| Scenario | Response time | Health check during it |
|---|---|---|
| 500-file batch, dispatch in request loop | 1.4-1.7 s | one check up to 1.1 s |
| 500-file batch, dispatch via `asyncio.to_thread` | 1.5-1.7 s | worst case 168 ms |

The remaining ~1.5 s and occasional slow health check come from 500
synchronous `.delay()` calls to Redis inside the dispatch loop. Moving the
loop to a worker thread let the event loop interleave other requests, but
some contention remains: the GIL means only one thread runs Python bytecode
at a time, so dispatch and other requests still take turns rather than
running simultaneously.

**Known next step:** Celery supports bulk/batch task dispatch, which would
reduce this to far fewer round-trips to Redis instead of 500 individual
calls. Not yet implemented.

## Status and results endpoints

- `GET /jobs/{batch_id}` — status, total/processed counts, cheap to poll
  repeatedly while a job runs
- `GET /jobs/{batch_id}/results` — full per-file results, available once
  the job is done; returns 404 until the results file exists

## Known limitations

- **Job records live in two places.** Live status and progress are in
  Redis; the final per-file results are written to a JSON file
  (`results/{batch_id}.json`), not a database. This was a deliberate
  short-term choice: a `jobs` table in PostgreSQL would support real
  queries ("all jobs with a rejection rate above 5% last week") that a
  folder of files can't, but that's deferred until Postgres is added for
  the feature data anyway, rather than standing up a database early just
  for this.
- Starlette's own multipart cap is 1000 files; the API's own limit (500) is
  lower and enforced explicitly with a 429, documented above.
- Two files with the same recording ID in one batch would be written
  concurrently to the same path in `processed/`. This does not occur in
  this dataset, but duplicates need an explicit policy.
- If the results file write fails after a batch completes, the job status
  becomes `completed_with_errors` and the raw results stay in Redis
  (under `job_results:{batch_id}`) rather than being deleted, so nothing
  is silently lost, but there is currently no alerting beyond a server log.
- Benchmarks are from one machine and one folder of the dataset (5,763 files).

## Run locally

Requires Redis running locally (`sudo systemctl start redis` on Fedora).

    python3 -m venv venv && source venv/bin/activate
    pip install -r requirements.txt

    # terminal 1: Celery worker
    celery -A tasks worker --loglevel=info

    # terminal 2: API server
    uvicorn main:app --reload

    # terminal 3: submit a batch, then poll
    curl -X POST http://127.0.0.1:8000/ingest -F "files=@path/to/file.json" ...
    curl http://127.0.0.1:8000/jobs/<batch_id>
    curl http://127.0.0.1:8000/jobs/<batch_id>/results

    # load test
    ./loadtest.sh /path/to/folder/of/json/files 500