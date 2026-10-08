# Design notes

Why the project is built the way it is: the problem, the architecture, and the real bugs that shaped it.

## The one-line version

A local, $0-cost pipeline that takes a job link, researches the company, and uses a local LLM (no API keys, no cloud inference cost) to generate a tailored CV and cover letter, written directly into a Google Doc — for up to 10 jobs in one batch from a Streamlit UI.

## The problem it solves

Applying to jobs well takes real effort per application: read the JD closely, work out what the company actually cares about, and rewrite the CV/cover letter to speak to that specific role rather than sending the same generic version everywhere. Doing that by hand for every job is slow, which either means fewer applications or worse-tailored ones. This automates the repetitive parts (fetching, researching, drafting) while keeping a human review step before anything gets sent, and costs nothing to run since it uses a model on your own machine instead of a paid API.

## Architecture, in order of what happens

```
Streamlit UI (or CLI)
   │  up to 10 job URLs / pasted JD text
   ▼
1. JD extraction        — jd_extractor.py (+ browser_fetch.py fallback)
2. Job-meta extraction  — llm.py: company + job title, via a cheap LLM call
3. Company research     — company_research.py: DuckDuckGo search + scrape
4. CV generation        — llm.py: local Ollama model (qwen3.5), from your
                           real CV + project notes + the JD + research
5. Cover letter gen     — llm.py: same model, from the tailored CV + JD +
                           research + project notes
6. Google Doc write     — docs_writer.py + cv_formatter.py: copies a
                           template doc, writes CV/cover letter into two tabs
                           with real formatting (headings, bold, bullets,
                           hyperlinks, margins)
   ▼
Google Doc link, ready to review
```

Everything is orchestrated by `pipeline.py`, which one job runs through end to end (`run_job`), and `run_batch` just loops that over however many jobs you gave it.

## The key design decisions (the "why", for an interview)

**Why a local LLM instead of an API (OpenAI/Anthropic/etc.)?**
Cost and volume. This runs potentially dozens of times a week; a paid API is fine at that scale too, but the requirement going in was zero ongoing cost. Ollama running a local model (`qwen3.5`, ~9.7B parameters, quantized) does this entirely offline after the one-time model download, with no per-request billing.

**Why Streamlit for the UI?**
It's the fastest way to get a real, usable form (10 URL fields, a submit button, live progress, results with doc links) without building a proper frontend. Free, local, and good enough — this is a personal tool, so a minimal web UI running on `localhost` is the right level of investment.

**Why not just use an "Ollama-MCP" integration or a no-code tool (Zapier)?**
This is a fixed, linear pipeline: fetch → research → generate → write. MCP earns its complexity when an LLM needs to *decide* which tool to call next; here the sequence never changes, so a plain Python script calling Ollama's REST API and Google's APIs directly is simpler, fully debuggable, and has no third-party dependency risk. Zapier's free tier also has task limits that this volume would burn through quickly, and it can't do the specific Google Docs "tabs" trick this project needed (see below).

**The hardest technical problem: Google Docs "tabs."**
The requirement was one Google Doc per application with two tabs (CV, Cover Letter). The Docs API cannot *create* new tabs via its `batchUpdate` endpoint — that's a real, current API limitation, not a bug in this code. The workaround: hand-make one template doc once, with the two tabs already there, then for every application, copy that template (Drive API `files.copy`) and overwrite each tab's body content by its `tabId`. Google recently extended most `batchUpdate` request types (insert text, delete range, paragraph style, bullets, margins) to accept a `tabId` field specifically for this multi-tab scenario, which is what makes the whole approach possible.

**Why does the CV get real formatting (headings, bold, bullets) but written as code, not just asked from the LLM?**
Early versions just asked the model to output the CV and inserted it as flat text — markdown asterisks and `#` symbols showed up literally in the doc, and margins/heading styles didn't exist at all. Local models are also not reliable enough to be trusted with "insert this exact heading style" instructions on their own. So the model is only asked to follow a **plain-text convention** (e.g. `**Title** | Org | Dates` for a job entry, `* ` for bullets, plain ALL CAPS for section headings) — deterministic enough for code to parse — and a dedicated parser (`cv_formatter.py`) converts that convention into actual Google Docs API formatting requests (bold ranges, real bullet lists, hyperlinks). The model writes content; the code guarantees the formatting. This same code path is also what enforces the CV fitting on two pages: Google's built-in Heading styles carry generous default spacing meant for long documents, so instead of using them at all, every paragraph gets an explicit, compact font size and spacing set directly (name larger and centered, section headings bold and small, body text tight), plus a hard rule that strips any blank line the model leaves before a section heading — belt-and-suspenders alongside a length budget in the prompt itself (max bullets per role).

**Why does the app force a specific section order and drop a section entirely, rather than just asking nicely?**
The tailored CV must keep the same sections in the same order as the master CV, and never include a Professional Certificates section. That is done in two places for the same content requirement: the section is removed from the source CV file entirely, *and* the prompt states the required order (read from the master CV's own headings, so a new section such as Projects is preserved automatically) and explicitly forbids inventing that section back in "even if you'd normally expect a CV to have one" (a plain instruction not to reorder wasn't reliable enough on its own, since the model would sometimes still nudge sections around).

**Why is the contact header (name, phone, location) force-overwritten after generation instead of trusting the model?**
Caught this directly during testing: even with an explicit "never invent contact details" instruction, the local model still hallucinated a plausible-but-wrong phone number and city on one run. Since this is exactly the kind of factual detail that must never be wrong, the code now always copies the name/contact line verbatim from the real CV file after generation, rather than relying on the model to reproduce it faithfully. This is a broader pattern worth being able to explain: for anything with a *correctness* requirement (not just a *style* requirement), don't trust an LLM's output blindly — verify or enforce it in code.

**Why is there a retry-and-reject loop around generation instead of just accepting whatever comes back?**
Two real bugs turned up in testing that motivated this: (1) the model sometimes generated an entire second cover letter appended inside the CV response, because the shared "Writing Style" instructions were ambiguous across what are actually two separate LLM calls; (2) with Ollama's default context window, a long combined prompt (CV + JD + research + reference letter) left too little room for output, so the model silently returned a near-empty response and the doc got written with nothing in it. Both are now caught: output length is validated, context size is computed from the actual prompt rather than a fixed default, and content is scanned for tell-tale contamination (a stray "Dear Hiring Manager" inside a CV, or CV section headings inside a cover letter) with one automatic retry before failing loudly instead of silently producing a broken doc.

**Why does the actual generation run in a background thread with results persisted to disk, instead of just running inline in the Streamlit script?**
This was a real bug found through actual use, not a design choice made up front: a batch could run for many minutes, and if the browser tab went idle (browser auto-sleep/discard is aggressive about this) or the page reconnected, Streamlit treated it as a brand new session and every in-memory result vanished — even though Ollama kept working in the background completely unaware anything had happened. The fix was to stop tying the actual work to any browser session at all: "Generate all" starts a plain background thread owned by the Streamlit *server process*, and every job's result is written to disk (`output/runs/<run_id>/`) the moment it finishes. The page just reads whatever's on disk on every render, so closing the tab, letting it sleep, or reopening the browser entirely all show current progress — the only thing that actually stops the work is closing the terminal window running the server itself. The general lesson: for anything long-running behind a web UI, don't assume the client staying connected is a safe assumption — decouple execution from the request/session lifecycle and make progress durable.

**Why does the JD extraction try three different methods?**
Job pages vary a lot: some are plain HTML (fast, simple `requests` + `trafilatura` works), some need a plainer text scrape because `trafilatura`'s boilerplate-stripping over-trims short pages, and some are pure JavaScript single-page apps that return an empty shell to a basic HTTP request (Workday, some Greenhouse/Lever embeds). For those, there's a headless-browser fallback (Playwright + Chromium) that actually renders the page like a real browser would before extracting text. Pages that are still just a login wall or bot-check get explicitly detected and rejected (rather than silently accepted as "content"), falling back to a manual paste box in the UI.

## Tools and libraries, and what each one is for

| Tool | What it's doing here |
|---|---|
| **Ollama** + **qwen3.5** (9.7B, quantized) | Local LLM inference — CV/cover letter generation, company/title extraction. No API cost. |
| **Streamlit** | The local web UI — 10 job-input rows, a submit button, live results. |
| **requests** + **trafilatura** + **BeautifulSoup** | Fetching and cleaning job description text from a URL. |
| **Playwright** (Chromium) | Headless-browser fallback for JS-only job pages that return no real content to a plain HTTP request. |
| **ddgs** (DuckDuckGo search) | Free, no-API-key company research — mission/values/news passages. |
| **Google Docs API** + **Google Drive API** (via `google-api-python-client`, OAuth) | Copies the template doc per application and writes the tailored content into its two tabs, with real formatting. |

## Known trade-offs

- Bullet-level bold formatting inside the CV is dropped for simplicity; only the entry-title line gets real bold.
- The model is non-deterministic, so identical inputs can produce a differently styled response between runs. That is why the CV formatter has fallback heuristics rather than assuming the model always follows the convention exactly.
- Generation is sequential: there is one local model, so parallel jobs would not be faster.
