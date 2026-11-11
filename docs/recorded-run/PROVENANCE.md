# Recorded run (offline fallback for the expo)

This is a **recorded** FlakeLab run, not a live one. Present it as such.

- Workflow: FlakeLab (extended), run 43053496319
  <https://github.com/Vachana7/flakelab/actions/runs/43053496319>
- Date: 2026-11-11, GitHub-hosted ubuntu runner, real Docker
- Target: `flakelab-demo:latest` on network `flakelab-net`, 10 runs per condition, 7 conditions
- Result: 13/13 diagnoses matched the planted causes (demo fixtures, not real-world evidence)

View it offline:

```
flakelab serve --dir docs/recorded-run
```
