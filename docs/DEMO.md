# Expo demo script

Expo date: **20 November 2026**. The main demo takes about 5 minutes and needs
**no internet and no GitHub token**. All commands are Windows PowerShell and
are run in the project folder (replace the path if yours differs).

Say the one-line idea first:

> "When someone changes a project's pipeline, my tool tells the reviewer what
> new powers the pipeline just gained, in plain words, before the change is
> accepted."

---

## 0. Setup the day before (needs internet, once)

```powershell
cd $HOME\Documents\pipedelta
git checkout platform
git pull
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pipedelta --help
```

Expected: `pipedelta --help` prints `usage: pipedelta [-h] {diff,git,action,serve} ...`.
If `Activate.ps1` is blocked, see problem 3 below.

Then run section 1 once with Wi-Fi switched off. If it works, it will work at the expo.

## 1. Start PipeDelta (do this 5 minutes before)

```powershell
cd $HOME\Documents\pipedelta
.\.venv\Scripts\Activate.ps1
Remove-Item Env:PIPEDELTA_GITHUB_TOKEN, Env:GITHUB_TOKEN, Env:GH_TOKEN -ErrorAction SilentlyContinue
Remove-Item demo.db -ErrorAction SilentlyContinue
pipedelta serve --db demo.db
```

Expected in the terminal: `PipeDelta 0.5.0 is running at http://127.0.0.1:8765`, then a line starting `GitHub token: not set`. If it says `set`, close this window, open a new one and repeat; the offline demo should run without a token. Leave this window open.
Open **http://127.0.0.1:8765** in Chrome. The left menu shows Overview, Analyze,
History, Repositories. Overview shows zeros because `demo.db` is new.

**Shortcut:** double-click `start-demo.bat` in the project folder. It does the same steps (no token, clean history, starts the server) and opens Chrome at the address after a few seconds. If Chrome does not open, type the address yourself. Keep the black window open.

The two `Remove-Item` lines make sure no token is set and the history is clean.
**The offline demo never uses a token. Do not type or paste a token during the expo.**

## 2. The demonstration

Click **Analyze**, then the **Examples** tab. Every example is analysed by the
real engine, with no internet.

| Step | What you click | Expected result |
|---|---|---|
| 1. Safe workflow | **An ordinary change** | **Low risk**, "Gate: pass", 1 finding (`actions/setup-python`, new in the file), 0 attack paths |
| 2. Malicious change | Go back, **A pull request adds a deploy job** | **High risk**, gauge **5**, "The GitHub Action would fail this change." |
| 3. Security findings | **Findings** tab | 5 findings, all High: unpinned action `some-stranger/format-helper`, contacts `collector.example.invalid`, token can change contents, reads secret `DEPLOY_TOKEN`, runs on `pull_request_target` |
| 4. Attack paths | **Attack paths** tab | 3 diagrams, each "Outside address" or "Unpinned outside code", then "Same job", then "Secret" or "Token that can write". Each shows "Made possible by this change" |
| 5. Finding details | **Findings** tab, click the first row | A side panel opens: High, Unpinned action, Written in file, line 11 |
| 6. Evidence and remediation | In the panel | Highlighted code on line 11, "Why it matters", and "What to do: replace the version tag with the full 40-character commit ID you reviewed" |
| 7. Move between findings | `j` or Down arrow, `k` or Up arrow | The panel shows the next or previous finding ("Finding 2 of 5") |
| 8. Show in diff | **Show in diff** in the panel | The Compare tab opens, the finding's line is highlighted |
| 9. Copy as PR comment | Open a finding, click **Copy for a PR comment** | Button says "Copied". Paste into Notepad: it starts with `**High: Runs unpinned action ...**` followed by Where, Why it matters, What to do |
| 10. Fixed workflow | **Analyze**, **Examples**, **The deploy job, fixed** | **Medium risk**, "Gate: pass", 1 finding (outside action, now locked to a commit), **No attack paths** |
| 11. History | **History** then **Overview** | Three runs listed; Overview counts are computed from them |

What to say at step 10: "The fix locked the outside action to a commit. The
attack paths are gone and the gate passes. It is still Medium because it is
still code from outside, so a person should still look. The tool does not claim
the pipeline is perfectly safe."

Other examples (optional): **Outsider text passed between jobs** and **Outsider
text passed between steps** both give **High risk**. They show text that an
outsider controls travelling through a job or step output into a command.

## 3. Troubleshooting

**1. `pipedelta` is not recognised.**
The virtual environment is not active. Run `.\.venv\Scripts\Activate.ps1`; the prompt then starts with `(.venv)`. If it still fails, use `py -m pipedelta serve --db demo.db`.

**2. `python` is not recognised.** Use `py` instead (the Windows launcher). That is why the commands above use `py`.

**3. Activate.ps1 is blocked by "running scripts is disabled".** Allow it for this window only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**4. "Address already in use" or the page does not load.** An old server is still running. Close the other PowerShell windows, or use another port:

```powershell
pipedelta serve --db demo.db --port 8766
```

and open `http://127.0.0.1:8766`. To see what holds port 8765: `Get-NetTCPConnection -LocalPort 8765`.

**5. The browser shows "This site can't be reached".** The server window was closed or crashed. Start it again with section 1. Use `http://127.0.0.1:8765` (`localhost` also works). The laptop's network address or any other host name is refused on purpose.

**6. An example does not open or the page looks broken.** Press Ctrl+Shift+R in Chrome to reload without cache. If it still fails, stop the server (Ctrl+C), delete `demo.db`, and start again.

**7. "Copy for a PR comment" says "Copy failed".** Chrome only allows copying from `127.0.0.1` or `localhost`; check the address bar. If it still fails, say "it copies the finding as Markdown" and show the Markdown report instead: **Download report**, **Markdown**.

**8. Everything fails.** Use the Docker fallback below, or open the HTML report you saved earlier. Before the expo, make one: in the app, open the malicious example, **Download report**, **HTML**, and keep the file on the Desktop. It is one file and needs no server.

**9. No Wi-Fi.** Nothing in the main demo needs it. The page loads no fonts, scripts or images from the internet. Only the live GitHub scenes below need it.

**Tokens.** Never put a GitHub token in a command, a document or a screenshot. If you ever typed one in this terminal, open the history file and delete that line, then revoke the token on GitHub:

```powershell
notepad (Get-PSReadLineOption).HistorySavePath
```

---

## 4. Optional: live GitHub scenes (needs internet and a signed-in browser)

You need a browser logged in to GitHub. Use this only if the internet is good;
the offline demo above covers the same ideas.

### Scene 1: an ordinary change passes (about 1 minute)

1. Open the repository on GitHub. Open `.github/workflows/ci.yml` and click the pencil (edit).
2. In the `matrix` line change `["3.10", "3.12"]` to `["3.10", "3.12", "3.13"]`.
3. Click **Commit changes**, choose **Create a new branch and start a pull request**, then **Propose changes** and **Create pull request**.
4. Wait about 40 seconds. The PipeDelta check turns green and its comment says the pipeline gained no new powers.

Say: "Testing on one more Python version changes the pipeline file, but gives it no new power. So it passes."

### Scene 2: a risky change is blocked (about 2 minutes)

1. Go back to the repository. Click **Add file → Create new file**.
2. Name it `.github/workflows/format.yml`.
3. Paste the contents of `examples/demo-paste.yml` (open it in another tab and copy).
4. Commit to a new branch and create the pull request, as in Scene 1.
5. Wait about 40 seconds. The PipeDelta check turns red and the comment lists the new powers.

Read two rows aloud and point at the matching lines in **Files changed**:

- "a command now contacts collector.example.invalid. The same job can read secrets, so they could be sent there."
- "now runs on pull_request_target, which people outside the project can set off."

Say: "This imitates a kind of pipeline attack: someone adds a small
workflow that reads a secret and sends it away. A reviewer who is in a
hurry sees ten lines of YAML. My tool turns those ten lines into sentences."

Be honest if asked: the address and the action in the demo do not exist. It
is an imitation, and nothing is actually stolen.

### Scene 3: fix it and watch the report change (about 1 minute)

1. In the same pull request, open **Files changed**, click the three dots on `format.yml`, then **Edit file**.
2. Delete the last three lines (the `curl` line and the two `env` lines) and change the `on:` line to `on: [workflow_dispatch]`. Do not use `pull_request` here: that would make GitHub try to run the demo file itself.
3. Commit to the same branch.
4. Wait. The same comment updates itself: the secret, the internet address and
   the risky trigger are gone. The check is still red, because two high-level
   powers remain: the token can still change the repository, and the outside
   action is still not locked to a commit.

Say: "The comment is not a new one. The tool edits its earlier report, so the
reviewer always sees the current state. And it is still blocked, which is
correct: I removed the theft, but the pipeline still has more power than it needs."

### After the live demo: reset

Close both pull requests without merging and delete their branches (GitHub
shows a **Delete branch** button after closing). Never merge the demo pull
requests.

## Offline fallback with Docker (no browser needed)

Run these in the repository folder. Build once before the expo while you have internet.

    docker compose build
    docker compose run --rm safe
    docker compose run --rm attack
    docker compose run --rm fixed

`safe` prints one low-level power and passes. `attack` prints five high-level
powers and stops with an error. `fixed` prints one medium-level power and passes.

Pull request #2 in the repository is also kept as a ready-made example in case
there is no time to create one live.

## Questions an examiner is likely to ask

**Where is Docker used?** The tool is packaged as a Docker image. GitHub
builds and runs that image for every pull request, the pipeline tests the
image, and it is published to GitHub's container registry. The offline demo
uses Docker Compose.

**Where is CI/CD used?** Two workflows. `ci.yml` tests the code on two Python
versions, builds the image, checks the image against the examples, and
publishes it. `pipedelta.yml` runs the tool on this repository's own pull
requests.

**Can an attacker just delete your check in the same pull request?** Yes,
unless the repository owner marks the check as required in branch settings.
This is written in the README under known limits.

**Does it catch every attack?** No. It reads workflow files only. It does not
look inside the outside actions a workflow calls, and it misses addresses
built from variables. It is meant to help a human reviewer, not replace one.

**How is it different from existing scanners such as zizmor?** Those tools
report problems in a workflow file as it is. PipeDelta reports what a change
added, in plain sentences. They can be used together. Comparing a base and a head
version of a workflow is not new: a tool called ci-delta (npm) already does that
and posts a pull request comment. From its public description I understand it
flags changes such as new triggers, wider token permissions and unpinned
actions; I have not run it, and I have not found a mention of effective
permissions or of following outsider text between jobs and steps. That
combination is what PipeDelta adds, but I have not compared the two on the
same cases, so I cannot say which finds more.

**How do you know the levels are right?** They are hand-written rules, and I
measured them two ways (`docs/EVALUATION.md`). On 12 attack cases that I
reconstructed from public reports, the first version blocked 6 of the 10 where
a workflow file changes; after I added two rules for the misses it blocked 8,
but that second number is not independent because I adjusted the tool to those
cases. On 1,659 real past workflow commits from eight Python projects, it
would have blocked about one in ten, mostly for outside actions that were not
locked to a commit. That is too noisy for a strict gate on a busy project, so
today it fits best as an advisory comment.

**What is the final state, in numbers?** Version 0.5 plus the web app.
Tests: 367 passing locally. Attack cases: 8 of 12 blocked at the default gate
(8 of 10 where a workflow file changes), not independent evidence because the
rules were tuned to them. Real history: 159 of 1,659 commits (9.6%) would be
blocked, which measures alert volume, not accuracy; nobody has judged which of
those alerts were wanted. Evidence for findings was checked over 2,808 real
file pairs (4,534 findings): no crash, no line number outside its file, 96.8%
located to the exact line. The step-output and job-output rules are tested on
constructed cases and have not fired on the real history.

**Is the web app safe to run?** It binds to localhost, refuses requests that
name another host or come from another website, and keeps the GitHub token in
the server's environment only. The token is never sent to the browser, and the
GitHub client refuses redirects away from api.github.com so the token cannot be
forwarded elsewhere. It has no login and is for one user on one computer.
