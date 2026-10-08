"""One-time helper: verifies your template Google Doc has the two tabs this
pipeline expects ("CV" and "Cover Letter"), confirms auth works, and saves the
doc ID to local_settings.json.

Usage (from the project root):
    python -m job_apply_agent.setup_template <TEMPLATE_DOC_ID>

You get <TEMPLATE_DOC_ID> from the URL of a Google Doc you create by hand:
https://docs.google.com/document/d/<THIS_PART>/edit
Create two tabs in it (use the tab bar on the left in Google Docs), named
exactly "CV" and "Cover Letter". Leave them empty or with placeholder text;
the pipeline clears and rewrites them on every run.
"""
import sys

from job_apply_agent import config, local_settings
from job_apply_agent.docs_writer import get_clients, tab_ids_by_title

REQUIRED_TABS = (config.TAB_NAME_CV, config.TAB_NAME_COVER_LETTER)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__)
        return 1

    doc_id = args[0].strip()
    clients = get_clients()
    document = clients.docs.documents().get(documentId=doc_id, includeTabsContent=True).execute()
    tabs = tab_ids_by_title(document)

    print(f"Found tabs: {list(tabs)}")
    missing = [tab for tab in REQUIRED_TABS if tab not in tabs]
    if missing:
        print(f"MISSING tab(s): {missing}. Add them in the Google Doc UI and re-run this check.")
        return 1

    local_settings.save({"template_doc_id": doc_id})
    print(f"Template looks good. Saved template_doc_id={doc_id} to {local_settings.SETTINGS_FILE.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
