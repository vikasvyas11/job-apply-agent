# Customising it

Most changes need no code. Edit the files in `content/` (or the Setup page); they are re-read on every run.

## Change what the documents say and how they sound

**`content/prompts.md`** holds the instructions sent to the model. It must contain three headings, on their own lines, exactly as written:

```
Prompt for Resume:
...
Prompt for Cover letter:
...
Writing Style:
...
```

- In the resume prompt, `[RESUME]` and `[COMPANY]` are filled in automatically.
- `Writing Style:` is appended to both requests; put your language variant (British/American English), banned phrases and tone rules there.
- To prefer certain stories in cover letters, name them in the cover letter prompt and describe them in `project_notes.md`.

**`content/resume.md`** is the source of truth. The tailored CV reproduces the ALL-CAPS section headings it finds there, in order, so adding a `PROJECTS` or `PUBLICATIONS` section is just a matter of adding it to this file.

**`content/project_notes.md`** is background the model may draw on but should never paste. One paragraph per role or project: the problem, what you did, the tools, the measurable outcome.

**`content/coverletter_reference.md`** fixes the shape of the letter (greeting, paragraph structure, sign-off). Write it once in a voice you like.

## Change the model

Set the Ollama model name on the Setup page (or `ollama_model` in `local_settings.json`), after `ollama pull <name>`. Notes:

- The request sets `think: false`, which suppresses hidden reasoning on "thinking" models. Models without that feature ignore it.
- `job_apply_agent/llm.py` sizes the context window to the prompt (`MIN_NUM_CTX` to `MAX_NUM_CTX`). If your model supports less than `MAX_NUM_CTX`, lower it.
- To use a hosted model instead (OpenAI, Anthropic, ...), replace `_call_ollama` in `llm.py` with a function returning `{"response": "<text>"}`. Everything else (validation, retries, formatting) is model-agnostic. Doing so means your CV leaves your machine, which this project otherwise avoids.

## Change the CV layout

`job_apply_agent/cv_formatter.py` turns the model's text into Google Docs formatting requests. The dictionaries `_FONT_SIZE_PT`, `_SPACING_PT`, `_ALIGNMENT` and `_BOLD_WHOLE_LINE` control size, spacing, alignment and bolding per line kind (`name`, `contact`, `heading`, `entry`, `bullet`, `normal`). Margins are `MARGIN_TOP_BOTTOM_PT` and `MARGIN_SIDES_PT` in `docs_writer.py`.

The length budget (how many bullets per role) lives in the `LENGTH` paragraph of `build_cv_prompt` in `llm.py`.

If you add a new line kind in `parse_cv`, add it to those dictionaries too, or it falls back to the `normal` style.

## Change the look

- **Colours of the native widgets** (buttons, inputs, tabs, the sidebar): the `[theme]` and `[theme.sidebar]` blocks in `.streamlit/config.toml`.
- **Layout, type and the custom pieces** (sidebar brand, result sheets, run meter, status chips): `job_apply_agent/theme.css`. The palette is a handful of variables at the top (`--ink`, `--desk`, `--proof`, `--marker`, ...); change those first.
- **Fonts:** the stylesheet uses only fonts that ship with Streamlit or the operating system, so the app makes no requests to font servers. If you add a web font, remember that it will.
- **What the pieces say:** the HTML fragments (brand, status, meter) are in `job_apply_agent/ui.py`; the page copy is in `app_pages/`. Escape anything that comes from outside the app (job titles, company names, URLs) with `html.escape` before putting it in a fragment.

## Use a different output

The final step of `pipeline.run_job` calls `docs_writer.create_application_doc`. To write Word files, Markdown or PDFs instead, replace that call with your own function that takes `company`, `job_title`, `cv_text` and `cover_letter_text` and returns a location string. The CV text uses a small fixed convention (`**Title** | Org | Dates`, `* ` bullets, ALL-CAPS headings), so it is easy to render anywhere.

## Add a job source

`jd_extractor.get_jd` is the only place that knows about fetching. To support a particular job board's API, add a branch there that returns a `JDResult(text=..., ok=True)`.

## Keep your data out of git

`.gitignore` already excludes `content/`, `output/`, `credentials.json`, `token.json` and `local_settings.json`. If you fork this repo to publish your own improvements, check before every push:

```bash
git status
git diff --cached --stat
```

and never remove those entries.

## Tests

```bash
pytest
```

The tests build a throwaway content and output folder, and stub out Ollama, Google and the network, so they are safe to run anywhere and are fast. When you change parsing, prompt assembly or retry behaviour, add a test next to the existing ones.
