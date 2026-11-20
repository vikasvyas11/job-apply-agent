# Job Application Agent

Paste a job link. Get back a **tailored CV and cover letter**, written into a formatted Google Doc, using an AI model that runs **on your own computer**. No subscriptions, no API keys, and your CV never goes to an AI company.

It fetches the job description, researches the company, rewrites your CV from a master copy you maintain, writes a cover letter in your voice, and files both into a copy of a Google Doc template (one tab each). Paste up to 10 links and leave it running.

> This is a drafting tool, not an autopilot. It selects and rewrites what is in *your* CV; it should never invent experience, but always read both documents before you send anything.

## How it works

```
 job URL(s) ──► fetch job description        (requests + trafilatura, headless-browser fallback)
                     │
                     ├──► company research     (DuckDuckGo search + page scrape, no API key)
                     ▼
              local LLM via Ollama ──► tailored CV  ──► cover letter
                     │
                     ▼
        Google Docs / Drive API ──► copy of your template doc, "CV" and "Cover Letter" tabs filled in
```

Highlights:

- **Local and free.** Generation uses [Ollama](https://ollama.com); the only external calls are fetching the posting, a web search for company background, and writing to *your own* Google Drive.
- **Your CV is the source of truth.** The model tailors from `content/resume.md`; contact details are copied from it in code, not trusted to the model.
- **Real document formatting.** Headings, bold titles, bullets, hyperlinks, margins and spacing are applied through the Docs API so the CV is two pages, not a text dump.
- **Guard rails around a small local model.** Context size is sized to the prompt, output length is validated, a CV that has a cover letter bleeding into it is rejected and retried, and common AI-cliche phrases trigger a redraft.
- **Survives a closed tab.** Work runs in a background thread and every result is saved to disk as it finishes.
- **Everything is editable without touching code:** a built-in Setup page for your name, CV, prompts, model and Google template.

## Requirements

- Windows, macOS or Linux
- Python 3.11 or newer
- [Ollama](https://ollama.com/download) and a model pulled into it (a few GB of disk, and enough RAM for the model you choose)
- A Google account and a free Google Cloud project (for the Docs and Drive APIs; about 10 minutes, once)

## Quick start

On this page, click the green **Code** button and copy the HTTPS link (or choose **Download ZIP** and unzip it). Then, in a terminal:

```bash
git clone <the link you copied>
cd job-apply-agent
```

**Windows:** double-click `setup.bat`, then `start.bat`.
**macOS / Linux:** `./setup.sh`, then `./start.sh`.

Then, in the browser tab that opens, work down the **Setup** page: your name, your CV, a cover letter you like, your Google Doc template, and a Google login. The first two Google steps (an OAuth client file and the template document) are described step by step in **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**; that guide also has a troubleshooting table.

When Setup shows green, go back to the main page, paste a job link and press **Generate all**. A job takes a few minutes on typical laptop hardware.

Prefer the command line? `python -m job_apply_agent --job-url "https://..."` (see `--help`).

## Make it yours

Each run uses one **flow** and one **region**, chosen at the top of the Applications page:

- **Flow**: *Data Science*, *Growth* or *Software Dev*. Each flow has its own master CV, project notes, cover letter reference and prompts, so you can present the same career three different ways. A run never reads the other flows' files.
- **Region**: *UK* or *India* by default (add your own). It fills the city and phone on the CV's contact line; cover letters never include them.

Everything personal lives in plain-text files in `content/<flow>/` (`data`, `growth`, `software`), which is git-ignored so you can never publish it by accident. The first run copies placeholder versions from `content.example/`.

| File (per flow) | What goes in it |
|---|---|
| `resume.md` | Your complete CV for this kind of role. The model selects from it. The contact line uses `{{LOCATION}}` and `{{PHONE}}`. |
| `coverletter_reference.md` | One cover letter in the voice you want, used for tone and structure only |
| `project_notes.md` | The real story behind your CV bullets: problem, what you built, outcome |
| `prompts.md` | The instructions given to the model, and your writing-style rules |

Open **`Documentation.html`** for the full illustrated guide.

See **[docs/CUSTOMISING.md](docs/CUSTOMISING.md)** for how to shape the output, change the model, adjust the CV layout, or send the result somewhere other than Google Docs.

## Privacy and security

- Your CV and the jobs you apply to stay on your machine. Nothing is sent to an AI provider.
- `credentials.json` (your Google OAuth client), `token.json` (your login), `local_settings.json`, `content/` and `output/` are all in `.gitignore`. **Never commit or share them.** If you ever do, revoke the OAuth client in the Google Cloud console and delete `token.json`.
- The app asks for the `drive` scope because it must copy a template document you created outside the app (the narrower `drive.file` scope cannot see it). It only touches the template and the copies it makes.
- Keep your OAuth consent screen on "Testing" with only yourself as a test user. Google expires test-mode logins after 7 days; reconnect from the Setup page when asked.

## Use it responsibly

- Review everything before sending. Small local models can still phrase things badly or overstate.
- Only apply to roles you genuinely qualify for; the tool tailors your real experience, it does not create it.
- Be considerate when fetching pages: it makes one request per posting plus a handful of searches. Some sites forbid automated access; where a fetch fails, paste the description instead.

## Project layout

```
streamlit_app.py     the web UI           app_pages/          Applications and Setup pages
job_apply_agent/     the package          tests/              pytest suite (no network needed)
content.example/     placeholder inputs   docs/               guides and technical reference
```

Technical reference: [docs/CODEBASE.md](docs/CODEBASE.md). Why it is built the way it is: [docs/DESIGN.md](docs/DESIGN.md).

## Development

```bash
pip install -r requirements-dev.txt
pytest          # ~70 tests, about a second, no Ollama or Google needed
ruff check .
```

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
