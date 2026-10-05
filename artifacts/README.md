# E2E artifacts

`setup-and-test.ps1` deletes screenshots from the previous run before every test.
It then writes fresh screenshots to `artifacts/screenshots/` and the machine-readable
result to `artifacts/e2e-report.json`. Unless `-NoPush` is supplied, changes are
committed and pushed even when the UI test fails, so the failing screen can be
inspected from GitHub.
