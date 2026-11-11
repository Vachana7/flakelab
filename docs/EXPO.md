# Expo script (21 November 2026)

Six scenes, about 8 minutes, plus questions. Everything runs offline on the laptop once the
images are built. Practise it at least twice with a timer.

## The day before: checklist

- [ ] Docker Desktop installed, running, and set to start on boot
- [ ] `git pull` in the `flakelab` folder
- [ ] `docker compose build` (downloads base images: needs internet, do it at home)
- [ ] `pip install .` in the `flakelab` folder (so `flakelab` works in PowerShell)
- [ ] One full rehearsal of all scenes **with Wi-Fi turned off**
- [ ] Browser tabs open: the GitHub repo **Actions** tab, a merged PR with the FlakeLab
      comment, the recorded dashboard
- [ ] Laptop charger, a mouse, font size increased in the terminal (Ctrl + mouse wheel)
- [ ] Offline fallback ready: `flakelab serve --dir docs/recorded-run` works (see below)

## Scene 1: The mystery (1 min)

> "Same code, nothing changed. Watch the test suite five times."

```powershell
docker compose up -d weather-api
1..5 | ForEach-Object { docker run --rm --network flakelab-net flakelab-demo:latest python -m pytest -q 2>&1 | Select-Object -Last 1 }
```

Results differ between runs (the token test and the weather tests fail now and then).

> "Rerunning tells me *that* something is flaky. It can't tell me *why*, because in a rerun
> everything varies at once and nothing is controlled. And some tests never fail here at all,
> but will fail on a different CI machine. Reruns can never find those."

## Scene 2: The experiment (2 min)

```powershell
$env:FLAKELAB_RUNS = 5
docker compose up --build flakelab dashboard
```

Open <http://localhost:8080>. In a second terminal:

```powershell
docker stats
```

> "FlakeLab starts a fresh container for every run and changes exactly one thing: a quarter of
> a CPU, 128 MB of memory, no network, reversed or shuffled order, a different timezone.
> In `docker stats` you can see the CPU-limited containers capped at 25%. That limit comes
> from Linux cgroups, the same mechanism Kubernetes uses."

## Scene 3: The investigation (1.5 min)

Point at the heatmap as it fills in. Click `test_authorize_within_sla`.

> "Ten out of ten failures with limited CPU, zero at baseline. Fisher's exact test says the
> chance of that by luck is below 0.1%, after correcting for testing six conditions. So
> FlakeLab reports a confirmed observation and a *supported hypothesis*: CPU / timing
> sensitivity. It never says 'root cause', because an association is not proof."

Click `test_session_tokens_unique`:

> "This one fails randomly under every condition. FlakeLab says 'unknown' instead of blaming
> a condition. Not guessing is a feature."

## Scene 4: Failure DNA (1 min)

Scroll to Failure DNA.

> "Each test has a DNA: its failure rate under each condition. These two weather tests share
> the same DNA (they only fail without network), and they also fail in the same runs, so one
> fix, mocking the weather service, probably repairs both. Research from 2025 found that 75%
> of flaky tests come in clusters like this."

## Scene 5: Reproduction capsule (1.5 min)

```powershell
flakelab run --runner docker --image flakelab-demo:latest --docker-network flakelab-net --runs 6 --conditions timezone_ist,reverse_order --out results
cd results/capsules/tests_test_reports.py__test_report_title
type README.md
./reproduce.ps1
flakelab capsule verify . --runs 5
```

> "Don't trust my diagnosis: reproduce it. The capsule records the exact test order of a
> failing run, the Docker settings, the image ID and every package version. One command
> replays it; `verify` re-runs it against a baseline and checks it statistically."

## Scene 6: CI/CD (1 min)

Show the GitHub tabs:
1. **Actions → CI**: quality checks → Docker builds → real-Docker integration test → capsule
   verification → images published to GitHub Container Registry.
2. **A pull request** with FlakeLab's comment: the report appears automatically on the PR.
3. **Evaluation** results (`docs/evaluation/EVALUATION.md`).

> "Every push runs the pipeline. Pull requests get a short experiment and a report as a
> comment. The full experiment and the evaluation run on demand, so CI cost stays bounded."

## Closing line

> "FlakeLab doesn't just detect flaky tests. It runs controlled experiments to find the
> conditions behind their failures, says how sure it is, and gives you a capsule to
> reproduce it yourself."

## Offline fallback

If Docker misbehaves on the day, open the recorded real run (from GitHub Actions):

```powershell
flakelab serve --dir docs/recorded-run
```

Say clearly: "This is a recorded run from GitHub's servers on <date>; here's the workflow
link." Never present recorded results as live.

## If something goes wrong

| Problem | Fix |
|---|---|
| `docker: error during connect` | Docker Desktop isn't running: start it, wait for the whale icon |
| Port 8080 in use | `docker compose down`, or change the port in `docker-compose.yml` |
| Weather tests fail even at baseline | `docker compose up -d weather-api` first |
| CPU test fails at baseline too | the laptop is busy: close other programs; explain host load is a known confounder |
| Everything slow | use `FLAKELAB_RUNS=3` for the live part and the recorded run for the full picture |
