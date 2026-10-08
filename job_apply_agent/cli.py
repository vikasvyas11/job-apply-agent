"""CLI entry point for running the pipeline without Streamlit.

Usage (from the project root):
    python -m job_apply_agent --job-url "https://..." [--job-url "https://..." ...]
    python -m job_apply_agent --job-url "https://..." --company "Acme"
"""
import argparse
import logging

from job_apply_agent.pipeline import JobInput, run_batch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job_apply_agent",
        description="Generate a tailored CV and cover letter for one or more job postings.",
    )
    parser.add_argument(
        "--job-url", action="append", required=True, dest="job_urls",
        help="Repeat this flag for multiple jobs (up to 10 recommended).",
    )
    parser.add_argument(
        "--company", action="append", default=[],
        help="Optional company name override, matched by position to --job-url.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if len(args.company) > len(args.job_urls):
        parser.error("more --company values than --job-url values")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    companies = args.company + [""] * (len(args.job_urls) - len(args.company))
    jobs = [
        JobInput(url_or_text=url, company_name=company)
        for url, company in zip(args.job_urls, companies, strict=True)
    ]

    results = run_batch(jobs)
    for result in results:
        print(f"\n=== {result.job.url_or_text} ===")
        for line in result.log:
            print(f"  - {line}")
        print(f"  DOC: {result.doc_url}" if result.ok else f"  ERROR: {result.error}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
