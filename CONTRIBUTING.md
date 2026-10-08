# Contributing

Bug reports and pull requests are welcome.

1. Fork the repo and create a virtual environment: `python -m venv .venv`, activate it, then `pip install -r requirements-dev.txt`.
2. Make your change. Add or update a test in `tests/` (they run in about a second and need no network, Ollama or Google).
3. Run `pytest` and `ruff check .` and make sure both pass.
4. Open a pull request describing the problem and the fix.

Please never include real CVs, cover letters, job applications, `credentials.json`, `token.json` or `local_settings.json` in an issue or pull request. Use the placeholders in `content.example/` or invented data.

For anything security related (for example, a way the app could leak a token), open a private security advisory on GitHub instead of a public issue.
