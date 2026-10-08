"""Google Docs/Drive writer.

The Docs API cannot create new tabs via batchUpdate yet, so the workflow is:
  1. You hand-make a template Doc once with two tabs: "CV" and "Cover Letter"
     (see SETUP.md / setup_template.py).
  2. For each job, copy that template (Drive API) to a new file.
  3. Clear and rewrite the body of each existing tab, targeted by tabId.
"""
import re
import time
from dataclasses import dataclass

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from job_apply_agent import config, cv_formatter

# 0.1" top/bottom, 0.3" sides, in points (1" = 72pt)
MARGIN_TOP_BOTTOM_PT = 0.1 * 72
MARGIN_SIDES_PT = 0.3 * 72

RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 2


def _execute_with_retry(request, *, attempts: int = RETRY_ATTEMPTS):
    """Runs a googleapiclient request's .execute(), retrying on transient
    network/server errors. Generation (the expensive, slow part) can succeed
    while this last, cheap write step fails on nothing more than a dropped
    connection — losing the whole job over that is wasteful, so retry before
    giving up. Real errors (bad request, not found, forbidden) are NOT
    retried, since retrying won't fix a wrong template ID or missing scope."""
    last_exc = None
    for attempt in range(attempts):
        try:
            return request.execute()
        except HttpError as exc:
            status = exc.resp.status if getattr(exc, "resp", None) else None
            if status is not None and status < 500 and status != 429:
                raise  # a real error — retrying won't help
            last_exc = exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            last_exc = exc  # covers WinError 10053 and similar dropped-connection cases
        if attempt < attempts - 1:
            time.sleep(RETRY_BASE_DELAY_SECONDS * (attempt + 1))
    raise last_exc


@dataclass
class GoogleClients:
    docs: object
    drive: object


def get_clients() -> GoogleClients:
    creds = None
    if config.GOOGLE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(config.GOOGLE_TOKEN_FILE), config.GOOGLE_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # Refresh token itself is dead — most commonly because this
                # OAuth client is in "Testing" publishing status in Google
                # Cloud Console, where Google auto-expires refresh tokens
                # after 7 days regardless of use. No way to silently recover
                # from this (there's no valid token left to refresh with) —
                # fall through to a full interactive re-auth instead of
                # crashing every job in the batch on a dead token.
                creds = None
        if not creds or not creds.valid:
            if not config.GOOGLE_CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Missing {config.GOOGLE_CREDENTIALS_FILE}. Download an OAuth "
                    "Desktop app client secret from Google Cloud Console and save it there "
                    "(see SETUP.md)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(config.GOOGLE_CREDENTIALS_FILE), config.GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)
        config.GOOGLE_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

    docs = build("docs", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return GoogleClients(docs=docs, drive=drive)


_BULLET_PREFIX_RE = re.compile(r"^(\*|-)\s+")
_HR_LINE_RE = re.compile(r"^(\*{3,}|-{3,}|_{3,})$")


def _clean_for_docs(text: str) -> str:
    """Strip lightweight markdown syntax the model tends to add, since a plain
    insertText call renders it literally rather than as formatting."""
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if _HR_LINE_RE.match(stripped):
            continue  # markdown horizontal rule — not real content
        stripped = stripped.lstrip("#").strip()
        stripped = stripped.replace("**", "").replace("__", "")
        stripped = _BULLET_PREFIX_RE.sub("• ", stripped)
        lines.append(stripped)
    return "\n".join(lines).strip() + "\n"


def tab_ids_by_title(document: dict) -> dict[str, str]:
    mapping = {}
    for tab in document.get("tabs", []):
        title = tab.get("tabProperties", {}).get("title", "")
        tab_id = tab.get("tabProperties", {}).get("tabId", "")
        mapping[title] = tab_id
    return mapping


def _tab_end_index(document: dict, tab_id: str) -> int:
    for tab in document.get("tabs", []):
        if tab.get("tabProperties", {}).get("tabId") == tab_id:
            body_content = tab.get("documentTab", {}).get("body", {}).get("content", [])
            if body_content:
                return body_content[-1].get("endIndex", 1)
    return 1


def _margin_request(tab_id: str) -> dict:
    return {
        "updateDocumentStyle": {
            "documentStyle": {
                "marginTop": {"magnitude": MARGIN_TOP_BOTTOM_PT, "unit": "PT"},
                "marginBottom": {"magnitude": MARGIN_TOP_BOTTOM_PT, "unit": "PT"},
                "marginLeft": {"magnitude": MARGIN_SIDES_PT, "unit": "PT"},
                "marginRight": {"magnitude": MARGIN_SIDES_PT, "unit": "PT"},
            },
            "fields": "marginTop,marginBottom,marginLeft,marginRight",
            "tabId": tab_id,
        }
    }


def _replace_tab_body(
    docs, document_id: str, tab_id: str, end_index: int, new_text: str, extra_requests: list[dict] = ()
):
    """Deletes the tab's existing content, inserts new_text, applies margins,
    and applies any extra formatting requests (paragraph styles, bold ranges,
    bullet lists, hyperlinks) — all in one batchUpdate so index math stays
    consistent (each request sees the document state left by the ones before
    it in the same call)."""
    requests_batch = []
    if end_index > 2:
        requests_batch.append(
            {
                "deleteContentRange": {
                    "range": {"tabId": tab_id, "startIndex": 1, "endIndex": end_index - 1}
                }
            }
        )
    requests_batch.append(
        {
            "insertText": {
                "location": {"tabId": tab_id, "index": 1},
                "text": new_text,
            }
        }
    )
    requests_batch.extend(extra_requests)
    requests_batch.append(_margin_request(tab_id))
    _execute_with_retry(docs.documents().batchUpdate(documentId=document_id, body={"requests": requests_batch}))


def _replace_cv_tab_body(docs, document_id: str, tab_id: str, end_index: int, raw_cv_text: str):
    """CV tab gets real formatting: centered Heading 1 name, centered contact
    line with working hyperlinks, Heading 2 section headings, bold entry
    titles, and real bullet lists — built by cv_formatter from the model's
    markdown-convention output."""
    specs = cv_formatter.parse_cv(raw_cv_text)
    plain_text, style_requests = cv_formatter.build_tab_content(tab_id, base_index=1, specs=specs)
    _replace_tab_body(docs, document_id, tab_id, end_index, plain_text, extra_requests=style_requests)


_UNSAFE_DOC_NAME_CHARS = re.compile(r"[\\/]")


def _doc_name(company: str, job_title: str) -> str:
    company = _UNSAFE_DOC_NAME_CHARS.sub("-", company).strip() or "Unknown Company"
    job_title = _UNSAFE_DOC_NAME_CHARS.sub("-", job_title).strip() or "Role"
    return f"{company} - {job_title} - {config.APPLICANT_NAME}"


def create_application_doc(
    clients: GoogleClients, *, company: str, job_title: str, cv_text: str, cover_letter_text: str
) -> str:
    """Copies the template, fills the CV and Cover Letter tabs, returns the new doc's URL."""
    if not config.TEMPLATE_DOC_ID:
        raise ValueError("config.TEMPLATE_DOC_ID is empty — run setup_template.py first.")

    # Belt-and-suspenders: never create a doc from empty/near-empty generation
    # output, even if something upstream failed to catch it.
    for label, text in (("CV", cv_text), ("cover letter", cover_letter_text)):
        if len(text.strip()) < 200:
            raise ValueError(
                f"Refusing to write to Google Docs: generated {label} text is only "
                f"{len(text.strip())} chars, which looks empty/broken rather than real content."
            )

    copy_metadata = {"name": _doc_name(company, job_title)}
    if config.OUTPUT_FOLDER_ID:
        copy_metadata["parents"] = [config.OUTPUT_FOLDER_ID]

    copied = _execute_with_retry(clients.drive.files().copy(fileId=config.TEMPLATE_DOC_ID, body=copy_metadata))
    new_doc_id = copied["id"]

    document = _execute_with_retry(
        clients.docs.documents().get(documentId=new_doc_id, includeTabsContent=True)
    )
    tab_ids = tab_ids_by_title(document)

    cv_tab_id = tab_ids.get(config.TAB_NAME_CV)
    cl_tab_id = tab_ids.get(config.TAB_NAME_COVER_LETTER)
    if not cv_tab_id or not cl_tab_id:
        raise ValueError(
            f"Template doc is missing a required tab. Found tabs: {list(tab_ids)}, "
            f"need both '{config.TAB_NAME_CV}' and '{config.TAB_NAME_COVER_LETTER}'."
        )

    _replace_cv_tab_body(clients.docs, new_doc_id, cv_tab_id, _tab_end_index(document, cv_tab_id), cv_text)
    _replace_tab_body(
        clients.docs, new_doc_id, cl_tab_id, _tab_end_index(document, cl_tab_id), _clean_for_docs(cover_letter_text)
    )

    return f"https://docs.google.com/document/d/{new_doc_id}/edit"
