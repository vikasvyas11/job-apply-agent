"""Setup page: every user-editable setting and content file, so nobody needs
to open a code editor to configure the app."""
import subprocess
from pathlib import Path

import requests
import streamlit as st

from job_apply_agent import config, docs_writer, local_settings, profiles, ui

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

    st.subheader("Contact details by region")
    st.caption(
        "Pick the region when you start a run. Its location and phone replace `{{LOCATION}}` and `{{PHONE}}` "
        "in the CV's contact line. Cover letters never include your location or phone."
    )
    edited_regions = {}
    for key, region in profiles.regions().items():
        col_name, col_loc, col_phone = st.columns([0.8, 2, 2], vertical_alignment="center")
        col_name.markdown(f"**{key}**")
        location = col_loc.text_input(f"{key} location", value=region.location, key=f"region_loc_{key}",
                                      placeholder="City")
        phone = col_phone.text_input(f"{key} phone", value=region.phone, key=f"region_phone_{key}",
                                     placeholder="Phone number")
        edited_regions[key] = {"location": location.strip(), "phone": phone.strip()}
    if st.button("Save contact details"):
        local_settings.save({"regions": edited_regions})
        st.success("Saved.")
        st.rerun()

# ------------------------------------------------------------------- Documents
with tab_docs:
    st.write(
        "Each flow has its own CV, cover letter reference, project notes and prompts. A run uses one flow "
        "only, so nothing from the other flows can end up in its documents."
    )
    flow = st.radio(
        "Flow to edit", options=list(profiles.FLOWS), format_func=profiles.FLOWS.get,
        horizontal=True, key="setup_flow",
    )
    folder = profiles.flow_dir(flow)
    label = profiles.FLOWS[flow]

    with st.expander(f"{label} CV", expanded=True):
        st.write(
            "Paste your **full** CV for this flow: every role, project and skill that suits it. The app "
            "selects and rewrites *from* this for each application. Keep the structure: your name, a contact "
            "line using `{{LOCATION}}` and `{{PHONE}}`, then ALL-CAPS section headings such as PROFESSIONAL SUMMARY, "
            "WORK EXPERIENCE and EDUCATION. The tailored CV keeps whichever headings you use, in this order."
        )
        _content_editor(folder / "resume.md", label="CV content", height=420, key=f"cv_text_{flow}",
                        save_label="Save CV")

    with st.expander(f"{label} cover letter style reference"):
        st.write(
            "A cover letter written in the voice and structure you want for this flow. Only its structure and "
            "tone are used; its content is never copied."
        )
        _content_editor(
            folder / "coverletter_reference.md", label="Cover letter reference", height=300,
            key=f"cl_text_{flow}", save_label="Save cover letter reference",
        )

    with st.expander(f"{label} project notes"):
        st.write(
            "The real story behind this flow's CV bullets: what the problem was, what you did, what happened. "
            "It makes cover letters specific instead of generic, and is never printed word for word."
        )
        _content_editor(
            folder / "project_notes.md", label="Project notes", height=320,
            key=f"notes_text_{flow}", save_label="Save project notes",
        )

    with st.expander(f"{label} prompts"):
        st.write(
            "The instructions given to the AI for this flow's CV and cover letter. Keep the three headings "
            "`Prompt for Resume:`, `Prompt for Cover letter:` and `Writing Style:` exactly as they are, because "
            "the app finds the sections by those names."
        )
        _content_editor(folder / "prompts.md", label="Prompts", height=420, key=f"prompts_text_{flow}",
                        save_label="Save prompts")

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
                ui.google_login_status.clear()
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
            ui.google_login_status.clear()  # the sidebar re-checks the new login straight away
            st.success("Connected.")
        except Exception as exc:
            st.error(f"Couldn't connect: {exc}")

st.write("")
if local_settings.is_configured():
    st.success("Basic setup is complete. Go to Applications to start generating.")
else:
    st.info("Add at least your name and a template document ID before generating your first application.")
