# Codebase documentation

Technical reference: file structure, what each module does, the data flow, and how to make common changes safely. For the "why" behind the design and an interview-ready explanation, see `PROJECT_EXPLAINER.md`. For one-time environment setup, see `SETUP.md`; for day-to-day use, see the top-level `README.md`.

## File structure

```
job-apply-agent/
├── streamlit_app.py          # entry point: theme, sidebar (brand, navigation, ready-check), runs the chosen page
├── app_pages/
│   ├── applications.py       # the queue of up to 10 job links, live progress, result sheets
│   └── setup.py              # name, CV, prompts, model, Google template + login
├── job_apply_agent/          # the Python package (all logic lives here)
│   ├── config.py             # paths, Google scopes; user settings are read live from local_settings.json
│   ├── local_settings.py     # load/save local_settings.json (name, template doc ID, model, Drive folder)
│   ├── profiles.py           # flows (data, growth, software) and regions; which content folder a run reads
│   ├── prompt_loader.py      # parses a flow's prompts.md into named sections at runtime
│   ├── jd_extractor.py       # fetches + cleans job description text from a URL (or accepts pasted text)
│   ├── browser_fetch.py      # headless-browser (Playwright) fallback for JS-only job pages
│   ├── company_research.py   # free DuckDuckGo search + scrape for company background (best-effort)
│   ├── llm.py                # Ollama client + prompt assembly + generation validation/retries
│   ├── cv_formatter.py       # parses the model's CV text, builds Google Docs formatting requests
│   ├── docs_writer.py        # Google Docs/Drive API: copies template, writes tab content + formatting
│   ├── ui.py + theme.css     # shared look and feel: stylesheet, status chips, run meter, readiness checks
│   ├── pipeline.py           # orchestrates one job (or a batch) end to end
│   ├── run_store.py          # persists batch-run progress/results to disk (output/runs/<run_id>/)
│   ├── cli.py / __main__.py  # command-line alternative to the UI: python -m job_apply_agent
│   └── setup_template.py     # one-time helper: verifies the template doc's tabs and saves its ID
├── content/                  # YOUR files (git-ignored): the LLM reads these fresh on every run
│   └── data/ growth/ software/   # one folder per flow, each with:
│       ├── resume.md             # that flow's full CV; contact line uses {{LOCATION}} and {{PHONE}}
│       ├── coverletter_reference.md  # a letter in the voice/structure wanted, style reference only
│       ├── project_notes.md      # detailed background per role/project, mined for narrative, never printed verbatim
│       └── prompts.md            # the instructions sent to the LLM for this flow
├── content.example/          # placeholder versions of the four files above, copied in on first run
├── tests/                    # pytest suite (no network, no Ollama, no Google)
├── docs/                     # SETUP.md, CODEBASE.md (this file), PROJECT_EXPLAINER.md
├── output/                   # git-ignored: runs/<run_id>/ results and exports/
├── credentials.json          # git-ignored: your Google OAuth client secret (you provide this)
├── token.json                # git-ignored: auto-created after first Google login
├── local_settings.json       # git-ignored: written by the Setup page
├── requirements.txt / requirements-dev.txt / pyproject.toml   # dependencies and ruff/pytest config
└── setup.bat / start.bat     # one-time install, and launcher for the UI
```

## Data flow (what calls what)

```
streamlit_app.py / cli.py
        │  builds JobInput(url_or_text, company_name, pasted_jd_fallback)
        ▼
pipeline.run_job(job)
        │
        ├─► jd_extractor.get_jd(...)              → JDResult(text, ok, error, source)
        │        └─► browser_fetch.fetch_rendered_html(...)   [fallback only]
        │
        ├─► llm.extract_job_meta(jd.text, ...)     → {"company": ..., "job_title": ...}
        │
        ├─► company_research.research_company(...) → ResearchResult(passages, sources)
        │
        ├─► llm.generate_cv(...)                   → tailored CV text (markdown convention)
        │        └─► llm.generate(...) → Ollama /api/generate  (with retry + validation)
        │        └─► llm._enforce_real_contact_header(...)     (forces correct contact line)
        │
        ├─► llm.generate_cover_letter(...)         → cover letter text
        │        └─► llm.generate(...) → Ollama /api/generate  (with retry + validation)
        │
        └─► docs_writer.create_application_doc(...)
                 ├─► Drive API: files.copy (template → new doc)
                 ├─► cv_formatter.parse_cv(...) + build_tab_content(...)   [CV tab]
                 ├─► Docs API: batchUpdate (delete + insert + style + bullets + links + margins)
                 └─► Docs API: batchUpdate (delete + insert + margins)     [Cover Letter tab, plain]
        ▼
JobResult(ok, company, job_title, doc_url, tailored_cv, cover_letter, log, error)
```

`pipeline.run_batch(jobs)` just authenticates with Google once, then calls `run_job` for each job in the list sequentially (not in parallel — there's one local model, so parallel generation wouldn't be faster).

## Module-by-module reference

### `config.py` and `local_settings.py`
Every path and API setting lives here; nothing is hardcoded elsewhere. Fixed values (file paths under the project root, Google scopes, tab names) are plain constants. The four user-editable values (`OLLAMA_MODEL`, `APPLICANT_NAME`, `TEMPLATE_DOC_ID`, `OUTPUT_FOLDER_ID`) are exposed as module attributes through a module-level `__getattr__`, which re-reads `local_settings.json` on every access. That matters because the Setup page saves while the Streamlit server is running: a value cached at import time would ignore those edits until a restart. `ensure_content_files()` copies any missing file from `content.example/` into `content/` without ever overwriting yours.
- `GOOGLE_SCOPES` must include full `drive` (not `drive.file`), because the template doc was created outside this app; `drive.file` would only grant access to files the app itself created.
- `local_settings.py` is the tiny JSON load/save layer behind the Setup page; a missing or corrupt file falls back to defaults.

### `profiles.py`
Defines the three flows (`data`, `growth`, `software`, with UI labels) and reads regions from `local_settings.json`. A `Profile(flow, region)` is created once per run and passed through `pipeline.run_batch` → `run_job` → `llm`; it is the only way content is located (`profile.resume_file`, `.project_notes_file`, `.cover_letter_reference_file`, `.prompts_file`), so a run cannot read another flow's files. `profile.render(text)` fills `{{LOCATION}}` and `{{PHONE}}` from the region, dropping a placeholder and its `|` separator when the value is empty.

### `prompt_loader.py`
Splits a flow's `prompts.md` (passed in as a path) into three named sections (`resume`, `cover_letter`, `writing_style`) by regex-matching its headings (`Prompt for Resume:`, `Prompt for Cover letter:`, `Writing Style:`). Raises a clear error if a heading is missing or renamed — so if you ever restructure `prompts.md`'s headings, either keep the exact wording or update the regexes in `_SECTION_HEADS`.

### `jd_extractor.py`
`get_jd(url_or_text, pasted_fallback)` is the entry point. If the input isn't a URL, it's treated as pasted JD text directly. If it is a URL:
1. Plain `requests.get` → `trafilatura.extract`, falling back to a BeautifulSoup plain-text scrape if that comes back short (`_extract_best_text`).
2. `_is_usable(text)` checks length **and** scans for junk markers (`"enable javascript"`, `"just a moment"`, `"sign in to continue"`, etc.) — a short page containing one of these is rejected outright, since it's very likely a JS-shell or bot-check, not real content.
3. If still not usable, falls back to `browser_fetch.fetch_rendered_html(url)` (a real headless Chromium render) and retries extraction on the rendered HTML.
4. If nothing works, returns `ok=False` with an error string; `pipeline.py` then relies on `pasted_jd_fallback` if the caller supplied one.

### `browser_fetch.py`
Thin wrapper around Playwright's sync API — launches headless Chromium, waits for `domcontentloaded` then (best-effort) `networkidle`, and returns the rendered HTML. Only invoked when the plain fetch path fails or looks like junk, since launching a real browser is much slower than a plain HTTP request.

### `company_research.py`
`research_company(company)` runs three DuckDuckGo queries (mission/values, recent news, product/engineering blog), scrapes the top result of each with `trafilatura`, and falls back to the search-result snippet if the scrape is too short. Returns a `ResearchResult` whose `.as_prompt_block()` formats everything as source-labeled text blocks — deliberately short (capped at ~1200 chars per passage) to leave room in the LLM's context window for everything else.

### `llm.py`
The core of the pipeline. Responsibilities:
- **`generate(prompt, min_output_chars=...)`** — calls Ollama's `/api/generate` with `think: False` (qwen3.5 is a reasoning model; leaving thinking on burns most of the generation budget on hidden chain-of-thought before any real output, which on CPU can run for many minutes) and a **dynamically sized `num_ctx`** (estimated from the prompt's length, not Ollama's small default, which would otherwise silently truncate a long prompt and starve the output). If the response comes back too short, it retries once at the maximum context size before raising `OllamaError`.
- **`extract_job_meta(jd_text, company_override)`** — a cheap, short LLM call that pulls `{"company": ..., "job_title": ...}` out of raw JD text, used to name the generated doc. Never raises; falls back to `"Unknown Company"` / `"Role"` if Ollama is unreachable or the response is unparsable.
- **`build_cv_prompt` / `build_cover_letter_prompt`** — assemble the full prompt sent to the model: the relevant section of `prompts.md`, the Writing Style section, the JD, company research, your CV dump / project notes, and a hard **STRUCTURE** block. That STRUCTURE block is what enforces the parseable markdown convention (`**Title** | Org | Dates` for entries, `* ` for bullets, plain ALL CAPS headings) that `cv_formatter.py` depends on, and explicitly scopes each call to *only* produce the one document (this exists because the model was observed bleeding a cover letter into the CV response when the shared Writing Style instructions were ambiguous about it).
- **`_enforce_real_contact_header(tailored_cv)`** — after generation, force-replaces everything before the `PROFESSIONAL SUMMARY` heading with the real name/contact line read directly from `content/resume.md`. This exists because the model was observed inventing a plausible-but-wrong phone number/location even when explicitly told not to — for anything factual like this, don't trust the model, enforce it in code.
- **`cv_section_headings(cv_dump)`**: reads the ALL-CAPS section headings out of the flow's `resume.md`, in order, and the CV prompt tells the model to reproduce exactly those. Adding a section to your CV (for example PROJECTS) is therefore all it takes for the tailored CV to keep it; no code or prompt edit needed.
- **`drop_invented_entries(tailored_cv, master_cv)`**: after generation, removes any job, project or education entry whose title (or, for a reworded title, organisation) is not in the flow's master CV, with its bullets, and gives every kept title the master CV's casing. Added after a real run invented a "v1" of a project and promoted background notes into a new entry.
- **`generate_cv` / `generate_cover_letter`** — the public entry points `pipeline.py` calls. Each retries generation (up to 2-3 attempts) if the output looks contaminated with the *other* document's markers (`_COVER_LETTER_MARKERS`, `_CV_SECTION_MARKERS`), and the cover letter additionally does a soft retry if it contains an obvious AI-cliche phrase from `_BANNED_PHRASES` (falls back to the best contamination-free attempt if none come back fully clean).

### `cv_formatter.py`
Turns the model's convention-following CV text into real Google Docs formatting, so the CV tab isn't just flat inserted text. Tuned to fit a two-page CV: compact custom typography rather than Google's default Heading styles (see below), and section headings must have no blank line before them.
- **`parse_cv(raw_text)`** — line-by-line classification into `LineSpec(text, kind, bold_len, links)`. The first two non-blank lines are always `name` and `contact` (guaranteed by `_enforce_real_contact_header`'s output shape upstream). After that: ALL-CAPS lines become `heading`; `**Title** | ...` lines become `entry` (with `bold_len` recording how much of the line to bold); a fallback heuristic catches entry-shaped lines the model forgot to bold (2+ `|` characters, not a bullet); `* ` lines become `bullet`; everything else is `normal`. Markdown links `[label](url)` are extracted into `(start, end, url)` ranges on every line via `_strip_md_links`, and stray backslash-escapes (`\-`, `\+`, from the source CV's own escaping style) are cleaned via `_unescape_md`. `_drop_blank_lines_before_headings` then strips any blank line immediately before a `heading` spec — belt-and-suspenders for the "no gap before a section" requirement, since the model doesn't always comply with the prompt instruction alone.
- **`build_tab_content(tab_id, base_index, specs)`** — walks the specs, computing each line's exact character offset in the tab, and returns `(plain_text_to_insert, style_requests)`. Every non-blank paragraph gets `NORMAL_TEXT` (deliberately, not `HEADING_1`/`HEADING_2` — Google's built-in heading styles carry generous default spacing meant for long documents, which read as unwanted gaps on a compact CV) plus explicit per-`kind` font size (`_FONT_SIZE_PT`) and paragraph spacing (`_SPACING_PT`, in points). Section headings and the name get bold + slightly larger size via `_BOLD_WHOLE_LINE`. Real bold, hyperlinks, and bullet lists (`createParagraphBullets`) are applied as before.
- This only runs on the **CV tab**. The Cover Letter tab uses the simpler `docs_writer._clean_for_docs` path (strip markdown, convert bullets to a literal `•` character) since it's prose, not a structured document with headings/entries.

### `docs_writer.py`
Everything that talks to the Google Docs/Drive APIs.
- **`get_clients()`** — handles the OAuth flow (first run opens a browser for consent; after that, `token.json` is reused and auto-refreshed).
- **`create_application_doc(...)`** — copies `config.TEMPLATE_DOC_ID` via Drive's `files.copy`, resolves the `CV` and `Cover Letter` tab IDs by title, and calls `_replace_cv_tab_body` / `_replace_tab_body` on each. Refuses to write anything if either generated text is under 200 chars (belt-and-suspenders against a broken/empty generation slipping through).
- **`_replace_tab_body(...)`** — the shared low-level operation: delete existing content → insert new text → apply any extra formatting requests → apply the 0.1"/0.3" margins. All of this is one `batchUpdate` call per tab, which matters because each request in a batch sees the document state left by the ones before it in the *same* call — that's what makes it safe to compute style ranges against text you just inserted in the same request.
- **Why `tabId` appears on almost every request** — this is a multi-tab document; without `tabId`, a request defaults to the *first* tab, silently writing to the wrong place.

### `pipeline.py`
Thin orchestration layer — no business logic of its own beyond sequencing the calls above and building the `JobResult` the UI/CLI displays. This is the file to read first to understand the whole flow at a glance. `run_batch` accepts an optional `on_result(idx, result)` callback, invoked right after each job finishes — this is what lets `streamlit_app.py` persist progress incrementally rather than only at the end.

### `run_store.py`
Disk persistence for a batch run: `new_run(n_jobs)` creates `output/runs/<run_id>/` and a `current_run.txt` marker; `save_job_result`/`load_job_results` write and read each job's result as its own JSON file; `read_status`/`write_status` track `{n_jobs, completed, done}`. Exists specifically so a run survives a Streamlit browser-session reset — see `streamlit_app.py` below for why that matters.

### `streamlit_app.py`, `app_pages/` and `ui.py`
`streamlit_app.py` is only the router: it sets the page config, injects `theme.css`, draws the sidebar (brand, page links, and the ready-check from `ui.current_checks()`), then runs the selected page. The look lives in three places: `.streamlit/config.toml` (native widget colours; also turns off Streamlit telemetry and binds the server to 127.0.0.1), `job_apply_agent/theme.css` (layout, type, the custom pieces), and `job_apply_agent/ui.py` (small HTML fragments and the readiness logic). Anything from outside the app (job titles, company names, URLs) is HTML-escaped in `ui.py` before it goes into a fragment. Result sheets are `st.container(key="sheet_ok_...")` / `sheet_fail_...`, which Streamlit exposes as CSS classes, so the stylesheet can colour the edge by status without relying on its internal markup.

`app_pages/applications.py`:
10 fixed input rows (URL, optional company override, optional pasted-JD fallback). Clicking "Generate all" starts a `threading.Thread` running `_worker(jobs, run_dir)` and returns immediately — the thread is owned by the **Streamlit server process**, not by any browser session, so it keeps running to completion even if the browser tab sleeps, disconnects, or is closed entirely (only closing the terminal running `streamlit run` stops it, since that kills the server process itself). A `st.cache_resource` registry remembers the worker thread, so a second tab or a double click cannot start a second batch that would compete for the single Ollama model. `pages/1_Setup.py` is the configuration page: name, CV, cover letter reference, prompts, project notes, Ollama model check/pull, Google template ID check and Google login. `_worker` calls `pipeline.run_batch` with an `on_result` callback that writes each job's result to disk via `run_store` as it completes. The page itself just reads whatever's on disk on every render (`_render_run`), auto-resumes the most recent run via `run_store.get_current_run()` on a fresh session, and offers a "Past runs" picker for anything earlier. This design exists because the original synchronous-in-script version lost all progress whenever the browser session was considered dead (tab sleep/discard, disconnect) even though Ollama kept working server-side, unaware anything had happened.

### `cli.py`
CLI equivalent, for scripting/quick tests without opening a browser: `python -m job_apply_agent --job-url "..." --job-url "..." --company "..."`. Exits non-zero if any job failed.

### `setup_template.py`
One-time helper: `python -m job_apply_agent.setup_template <DOC_ID>` confirms the doc has both required tabs (`CV`, `Cover Letter`) and that auth works, then saves the ID to `local_settings.json`. The Setup page does the same thing from the browser.

## How to make common changes

**Change how the CV/cover letter are written (tone, priorities, what to emphasize)**
→ Edit the flow's `content/<flow>/prompts.md`. No code changes, no restart needed — every generation call re-reads it fresh. Keep the three headings (`Prompt for Resume:`, `Prompt for Cover letter:`, `Writing Style:`) exactly as they are, since `prompt_loader.py` matches on them.

**Update your actual experience**
→ Edit the flow's `content/<flow>/resume.md` (keep it as the full superset of experience — the model selects *from* it, it doesn't need to already be trimmed) and/or `content/project_notes.md` (richer narrative detail, mined for cover-letter storytelling, never printed verbatim).

**Change the LLM model**
→ the Setup page (stored in `local_settings.json`). Pull it first (`ollama pull <name>`). If it's not a thinking/reasoning model, the `"think": False` flag in `llm._call_ollama` is a no-op (harmless either way).

**Change the CV's visual formatting** (font size, spacing, add a new line "kind", change bullet style)
→ `cv_formatter.py`. `_FONT_SIZE_PT` / `_SPACING_PT` / `_ALIGNMENT` / `_BOLD_WHOLE_LINE` dicts control per-`kind` styling; `build_tab_content` is where new request types would get added (e.g. color, italics). If you add a new line "kind" to `parse_cv`, remember to add entries for it in those dicts too, or it silently falls back to the `normal` defaults.

**The CV is running long / not fitting two pages**
→ Two levers: (1) `llm.py`'s CV prompt has a LENGTH block instructing bullet counts per role — tighten those numbers if needed; (2) `cv_formatter.py`'s `_SPACING_PT`/`_FONT_SIZE_PT` control the actual vertical space per line — reduce further if content length is already at the instructed limit and it still doesn't fit.

**Something isn't parsing as expected in the CV tab (wrong bold, missing heading, etc.)**
→ First check the model actually followed the convention: call `llm.generate_cv(...)` directly and print the raw output (see the debugging pattern used during development — write a small script under a scratch/temp directory, don't inline unicode through a Windows shell's `-c` flag, it mangles non-ASCII). Then check `cv_formatter.parse_cv(raw_text)` line-by-line against that raw output. The convention is deliberately simple (bold only wraps entry titles, bullets are plain) specifically so this stays debuggable.

**Add a new tab to the template doc / restructure the Google Doc output**
→ Not currently supported by the Docs API at all (`insertTab` doesn't exist in `batchUpdate`) — you'd need to hand-create any new tab in the template doc itself, then reference it in `docs_writer.py` the same way `CV`/`Cover Letter` are referenced (`config.TAB_NAME_CV` / `TAB_NAME_COVER_LETTER` pattern).

**The app can't reach Google Docs / Drive**
→ Delete `token.json` and re-run (or click Connect Google account on the Setup page); it'll re-trigger the OAuth browser flow. If that fails with a 404 on `files.copy`, check `config.GOOGLE_SCOPES` still includes full `drive` (not `drive.file`) — see the comment in `config.py` explaining why.

**Generation is failing / timing out**
→ Check `ollama list` shows the model pulled and `ollama serve` (or the Ollama app) is running. `llm.OllamaError` messages are written to include the estimated prompt size, the `num_ctx` used, and Ollama's `done_reason` — that's usually enough to tell whether it's a context-size issue, a genuinely unreachable server, or the model choking on the prompt.

## Known limitations (worth knowing before extending this)

- Bullet-level bold/inline formatting is dropped by design (only entry-title bold is preserved) — a deliberate simplicity trade-off, not an oversight.
- The local model is non-deterministic (temperature 1 by default) — identical inputs can produce differently-formatted output between runs, which is why `cv_formatter.py` has a fallback heuristic for entry detection rather than assuming the model always emits exact `**Title**` markup.
- JD extraction still can't get past a genuine login wall (e.g. some LinkedIn views) — the paste-fallback box in the UI is the intended escape hatch for those, not a bug to fix.
- Generation runs sequentially; batching 10 jobs is roughly 10x one job's generation time, not faster in parallel, since there's a single local model instance.

## Testing and code quality

```
.venv\Scripts\python -m pytest        # 70+ tests, ~1 second, no network / Ollama / Google needed
.venv\Scripts\python -m ruff check .   # lint
```

The tests run against a throwaway `content/` + `output/` tree (see `tests/conftest.py`), so they can never read or overwrite your real CV, settings or runs. They cover the pure logic that has caused real bugs: the CV parser and Docs offset maths, prompt assembly and the contamination/retry loops, the JD usability checks, run persistence, the pipeline's per-job error isolation, and the Docs retry policy. Calls to Ollama, Google and the web are always stubbed.
