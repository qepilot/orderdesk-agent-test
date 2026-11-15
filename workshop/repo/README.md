# OrderDesk (practice codebase)

A small orders-and-invoices REST API with a SQLite database and a test suite. It is the system the GitHub
Engineering Assistant investigates. **It contains defects on purpose**; the issues and pull requests in
`../github/` describe them from a reporter's point of view, without giving the answers.

```bash
python ../seed.py                 # build ../orderdesk.db (done automatically by the labs)
python -m pytest -q               # run the tests: one fails on purpose (issue #103)
python -m orderdesk               # serve the API on http://127.0.0.1:8040
```

See `docs/ARCHITECTURE.md` for the layout and the rules the code is supposed to follow.
