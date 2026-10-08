"""Setup page: every user-editable setting and content file, so nobody needs
to open a code editor to configure the app."""
import subprocess
from pathlib import Path

import requests
import streamlit as st

from job_apply_agent import config, docs_writer, local_settings, ui

config.ensure_content_files()
settings = local_settings.load()

ui.page_header(
    "Setup",
    "Everything here is saved on this computer. Nothing is sent anywhere until you generate an application.",
)

ui.checks_row(ui.current_checks())


def _content_editor(path: Path, *, label: str, height: int, key: str, save_label: str) -> None:
    """A text area bound to one content file, with its own save button."""
    text = st.text_area(label, value=path.read_text(encoding="utf-8"), height=height, key=key,
                        label_visibility="collapsed")
    if st.button(save_label, key=f"save_{key}"):
        path.write_text(text, encoding="utf-8")
        st.success("Saved.")


tab_profile, tab_docs, tab_model, tab_google = st.tabs(["Profile", "Documents", "AI model", "Google"])

# --------------------------------------------------------------------- Profile
with tab_profile:
    st.subheader("Your name")
    st.caption("Used to name the generated documents and to sign your cover letters.")
    name = st.text_input("Your full name", value=settings["applicant_name"], placeholder="Jane Smith",
                         label_visibility="collapsed")
    if st.button("Save name"):
        local_settings.save({"applicant_name": name.strip()})
        st.success("Saved.")
        st.rerun()

# ------------------------------------------------------------------- Documents
with tab_docs:
    with st.expander("Your CV", expanded=True):
        st.write(
            "Paste your **full** CV: every role, every project, every skill, not a trimmed-down version. "
            "The app selects and rewrites *from* this for each application, so more (accurate) detail means "
            "better tailoring. Keep the structure: your name, a contact line, then ALL-CAPS section headings "
            "such as PROFESSIONAL SUMMARY, WORK EXPERIENCE and EDUCATION. The tailored CV reproduces whichever "
            "headings you use here, in this order."
        )
        _content_editor(config.CV_DUMP_FILE, label="CV content", height=420, key="cv_text", save_label="Save CV")

    with st.expander("Cover letter style reference"):
        st.write(
            "Paste a cover letter written in the voice and structure you want. A real one you wrote before is "
            "ideal. Only its structure and tone are used; its content is never copied."
        )
        _content_editor(
            config.COVER_LETTER_REFERENCE_FILE, label="Cover letter reference", height=300,
            key="cl_text", save_label="Save cover letter reference",
        )

    with st.expander("Project notes"):
        st.write(
            "The real story behind your CV bullets: what the problem was, what you built, what happened. "
            "It makes cover letters specific instead of generic, and is never printed word for word."
        )
        _content_editor(
            config.PROJECT_NOTES_FILE, label="Project notes", height=320,
            key="notes_text", save_label="Save project notes",
        )

    with st.expander("Prompts"):
        st.write(
            "The instructions given to the AI for the CV and the cover letter. Change tone, priorities or "
            "structure here. Keep the three headings `Prompt for Resume:`, `Prompt for Cover letter:` and "
            "`Writing Style:` exactly as they are, because the app finds the sections by those names."
        )
        _content_editor(config.PROMPTS_FILE, label="Prompts", height=420, key="prompts_text", save_label="Save prompts")

# -------------------------------------------------------------------- AI model
with tab_model:
    st.subheader("Local AI model")
    st.write(
        "The writing is done by a model running on this computer through [Ollama](https://ollama.com/download): "
        "free, no API key, nothing sent to the cloud. Install Ollama first if you haven't."
    )
    model_name = st.text_input("Ollama model name", value=settings["ollama_model"])
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Save model name"):
            local_settings.save({"ollama_model": model_name.strip()})
            st.success("Saved.")
    with col2:
        if st.button("Check Ollama"):
            try:
                resp = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                if model_name in models:
                    st.success(f"Ollama is running and '{model_name}' is pulled.")
                elif models:
                    st.warning(f"Ollama is running, but '{model_name}' isn't pulled yet. Found: {', '.join(models)}")
                else:
                    st.warning("Ollama is running, but no models are pulled yet. Use 'Pull model'.")
            except requests.RequestException:
                st.error(
                    "Can't reach Ollama. Make sure it's installed and running "
                    "(it usually starts automatically after installing)."
                )
    with col3:
        if st.button("Pull model (a few GB, one time)"):
            with st.spinner(f"Pulling {model_name}. This can take several minutes depending on your connection."):
                try:
                    result = subprocess.run(
                        ["ollama", "pull", model_name], capture_output=True, text=True, timeout=3600, check=False
                    )
                    if result.returncode == 0:
                        st.success(f"'{model_name}' pulled successfully.")
                    else:
                        st.error(f"Pull failed:\n{result.stderr[-2000:]}")
                except FileNotFoundError:
                    st.error("'ollama' command not found. Install it from https://ollama.com/download first.")
                except subprocess.TimeoutExpired:
                    st.error("Pull timed out after an hour. Check your connection and try again.")

# ---------------------------------------------------------------------- Google
with tab_google:
    st.subheader("Google Doc template")
    st.write(
        "Create a blank Google Doc and add two tabs (the tab icon in the left panel of Google Docs) named "
        f"**exactly** `{config.TAB_NAME_CV}` and `{config.TAB_NAME_COVER_LETTER}`. Then copy its ID from the URL, "
        "`https://docs.google.com/document/d/`**`THIS_PART`**`/edit`, and paste it below."
    )
    template_id = st.text_input("Template Google Doc ID", value=settings["template_doc_id"])
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Save template ID"):
            local_settings.save({"template_doc_id": template_id.strip()})
            st.success("Saved.")
    with col2:
        if st.button("Verify template"):
            try:
                clients = docs_writer.get_clients()  # may open a browser for first-time consent
                doc = clients.docs.documents().get(documentId=template_id.strip(), includeTabsContent=True).execute()
                tabs = list(docs_writer.tab_ids_by_title(doc))
                missing = [t for t in (config.TAB_NAME_CV, config.TAB_NAME_COVER_LETTER) if t not in tabs]
                if missing:
                    st.error(f"Found tabs {tabs}, missing: {missing}. Add them in the Google Doc and try again.")
                else:
                    st.success(f"Template looks good. Found tabs: {tabs}")
            except Exception as exc:
                st.error(f"Couldn't verify: {exc}")

    st.subheader("Connect your Google account")
    st.write(
        "Do this the first time. A browser window opens asking you to sign in and approve access to Google "
        "Docs and Drive. After that, it's remembered."
    )
    if st.button("Connect Google account"):
        try:
            docs_writer.get_clients()
            st.success("Connected.")
        except Exception as exc:
            st.error(f"Couldn't connect: {exc}")

st.write("")
if local_settings.is_configured():
    st.success("Basic setup is complete. Go to Applications to start generating.")
else:
    st.info("Add at least your name and a template document ID before generating your first application.")
