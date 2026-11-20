# Getting started

A complete walkthrough from nothing to your first generated application. Budget about 30 minutes, most of it the one-off Google Cloud setup and the model download.

1. [Install the prerequisites](#1-install-the-prerequisites)
2. [Get the code and install it](#2-get-the-code-and-install-it)
3. [Create a Google OAuth client](#3-create-a-google-oauth-client)
4. [Create the template Google Doc](#4-create-the-template-google-doc)
5. [Pull a model](#5-pull-a-model)
6. [Start the app and complete Setup](#6-start-the-app-and-complete-setup)
7. [Generate your first application](#7-generate-your-first-application)
8. [Troubleshooting](#8-troubleshooting)

## 1. Install the prerequisites

| Tool | Why | Check it |
|---|---|---|
| **Python 3.11+** | runs the app | `python --version` (on macOS/Linux often `python3 --version`) |
| **Ollama** | runs the AI model locally, free | `ollama --version` |
| **Git** (optional) | to clone the repo; you can also download the ZIP from GitHub | `git --version` |

- Python: https://www.python.org/downloads/. On Windows tick **Add python.exe to PATH**.
- Ollama: https://ollama.com/download. Run the installer; it starts a background service on `localhost:11434`.

## 2. Get the code and install it

On the repository's GitHub page, click the green **Code** button and copy the HTTPS link (or choose **Download ZIP**, unzip it, and open a terminal in the unzipped folder). Then:

```bash
git clone <the link you copied>
cd job-apply-agent
```

If you downloaded the ZIP, the folder may be called `job-apply-agent-main`; open a terminal inside it instead of running the two commands above.

Then run the installer for your system. It creates a private virtual environment in `.venv/`, installs the dependencies, and downloads the headless Chromium used as a fallback for JavaScript-only job pages.

- **Windows:** double-click `setup.bat`
- **macOS / Linux:** `./setup.sh`

Doing it by hand instead:

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

## 3. Create a Google OAuth client

The app writes to Google Docs on your behalf, so Google needs to know which application is asking. You create that "application" yourself, for free, and it only ever serves you.

1. Open https://console.cloud.google.com/ and create a project (any name, e.g. `job-apply-agent`).
2. **APIs & Services > Enable APIs and services.** Search for and enable both **Google Docs API** and **Google Drive API**.
3. **APIs & Services > OAuth consent screen** (may be called "Google Auth Platform"):
   - User type: **External**.
   - Fill in an app name and your email.
   - Under **Test users**, add your own Google account.
   - Leave the publishing status on **Testing**. You do not need Google's verification for personal use.
4. **APIs & Services > Credentials > Create credentials > OAuth client ID.** Application type: **Desktop app**. Create it.
5. Download the JSON and save it as **`credentials.json` in the project root**, next to `streamlit_app.py`.

> `credentials.json` is a secret. It is already in `.gitignore`. Do not upload or share it.

## 4. Create the template Google Doc

Google's Docs API cannot create new tabs, so the app works from a template you build once: for every job it copies the template, then fills in the two tabs.

1. Create a new blank Google Doc.
2. Add two tabs (the tab icon in the left panel, or the `+` beside **Tabs**) and name them **exactly**:
   - `CV`
   - `Cover Letter`
3. Leave them empty. The app clears and rewrites them on every run and sets the margins, fonts and spacing itself.
4. Copy the document ID from the URL: `https://docs.google.com/document/d/`**`THIS_PART`**`/edit`.
5. Optional: create a Drive folder for the output, and copy its ID from the folder URL (`.../folders/THIS_PART`). Generated documents are then filed there instead of loose in My Drive.

## 5. Pull a model

```bash
ollama pull qwen3.5:latest
```

That is the default. Any model Ollama can run works; pick one that fits your machine and set its name on the Setup page. As a rule of thumb, bigger models write better but are slower; on a laptop without a GPU expect a few minutes per application with a mid-sized model. Browse https://ollama.com/library.

## 6. Start the app and complete Setup

- **Windows:** double-click `start.bat`
- **macOS / Linux:** `./start.sh`

A browser tab opens at `http://localhost:8501`. **Keep the terminal window open**; closing it stops the app. Open **Setup** in the sidebar and go down the page:

1. **Your details.** Your full name. It names the generated documents and signs the cover letters.
2. **Your CV.** Replace the placeholder with your complete CV. See [what the CV file needs](#what-the-cv-file-needs) below.
3. **Cover letter reference.** One real cover letter in the tone you want. Only structure and voice are copied, never its content.
4. **Prompts.** Sensible defaults are pre-filled. Edit later once you have seen some output.
5. **Project notes.** Optional but worth the effort: the real story behind your bullets.
6. **Local AI model.** Type the model name, **Check Ollama** to confirm it is running and pulled.
7. **Google Doc template.** Paste the document ID, **Save**, then **Verify template**. The first verification opens a browser window for Google login; approve it. If Google says the app is unverified, choose Advanced > continue (it is your own app).
8. **Connect Google account.** Only needed if step 7 did not already log you in.

Add the optional Drive folder ID in `local_settings.json` (`output_folder_id`) if you want one.

### What the CV file needs

Each flow (`content/data/`, `content/growth/`, `content/software/`) has its own CV; fill in at least the flows you will use. The parser relies on a simple shape. Use `content.example/data/resume.md` as a model.

- **Line 1:** your name. **Line 2:** your contact line, with `{{LOCATION}}` and `{{PHONE}}` where your city and phone go (filled from the region you pick) and links as `[label](https://...)`.
- Set each region's city and phone on the Setup page under **Profile**.
- **Section headings in ALL CAPS** (`PROFESSIONAL SUMMARY`, `WORK EXPERIENCE`, `EDUCATION`, `PROJECTS`, `TECHNICAL SKILLS`, ...). Whatever headings you use, in whatever order, are the ones the tailored CV keeps.
- **Entries:** `**Job Title** | Organisation, Location | Mon YYYY - Mon YYYY`
- **Bullets:** lines starting with `* `.
- Put in **everything**: every role, project and skill. The model selects the relevant parts per job, so a longer, accurate master CV gives better results than a trimmed one.

## 7. Generate your first application

At the top of the page choose the **Application type** (the flow: Data Science, Growth or Software Dev) and the **Region**. Every link in the batch uses that flow's CV and prompts only, so put one type of job in each run.

1. On the main page paste a job URL into **Job 1**. Optionally add the company name, and paste the job description in the box underneath if you expect the link to be blocked (LinkedIn usually is).
2. Click **Generate all**. You can add up to 10 jobs; they run one after another.
3. Watch progress on the page, or close the tab and come back later. Results are saved as they finish.
4. Each finished job shows the tailored CV, the cover letter, and an **Open Google Doc** link. Open it, read both tabs, edit freely, and export to PDF from Google Docs when you are happy.

Past runs are listed under **Past runs** and stored in `output/runs/`.

## 8. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `Error 403: access_denied` when logging in to Google | Your account is not listed as a **Test user** on the OAuth consent screen. Add it (step 3) and retry. |
| Google login suddenly required again after about a week | Normal for apps in Testing mode (refresh tokens expire after 7 days). Click **Connect Google account** on Setup, or delete `token.json`. |
| `An Application Control policy has blocked this file` when starting Python (Windows) | Windows Smart App Control blocks unsigned programs, and some Python builds (for example ones installed by `uv`) ship an unsigned `python.exe`. Install Python from https://www.python.org/downloads/ (it is signed), delete the `.venv` folder and run `setup.bat` again. You do not need to turn Smart App Control off. |
| `Missing .../credentials.json` | Step 3.5: the file must be named exactly `credentials.json` and sit in the project root. |
| `404` from Drive on `files.copy` | Wrong template ID, or the account you logged in with cannot open the template. Re-verify on Setup. |
| `Template doc is missing a required tab` | The tabs must be named exactly `CV` and `Cover Letter` (case and spacing matter). |
| `Could not reach Ollama` | Start Ollama (it is usually a tray/menu-bar app) and run `ollama list` to confirm your model is there. |
| Model returns very short or empty output | The prompt may exceed what the model handles. The app already enlarges the context and retries once; try a different model, or shorten `project_notes.md`. |
| Very slow generation | Normal on CPU. Use a smaller model, or close other heavy programs. |
| Job link fails to fetch | Login walls and bot checks cannot be crossed. Paste the job description into the box under the link. |
| CV spills onto a third page | Tighten the bullet counts in the LENGTH block of `build_cv_prompt` in `job_apply_agent/llm.py`, or reduce sizes in `job_apply_agent/cv_formatter.py`. |

Still stuck? Run a single job from the command line to see the full error text:

```bash
python -m job_apply_agent --job-url "https://example.com/job"
```

## Updating

```bash
git pull
pip install -r requirements.txt     # inside the virtual environment
```

Your `content/`, `credentials.json`, `token.json`, `local_settings.json` and `output/` are untouched by updates.
