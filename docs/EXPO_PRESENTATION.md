# Expo demonstration guide: presenting PipeDelta to experts

Setup steps are in `docs/SETUP.md`. This guide is what to say and do. Total:
about 6 minutes of talk and demo, then questions.

## Before you go on (10 minutes earlier)

1. `cd $HOME\Documents\pipedelta`, activate `.venv`, set your token with the hidden prompt, run `pipedelta serve`, open http://127.0.0.1:8765.
2. Click **Analyze, Examples, "A pull request adds a deploy job"** once so Overview has data. Then click the repo connect once to confirm GitHub works.
3. Have the slides open in one tab and the web app in another. Close notifications.
4. Know your fallback: if the Wi-Fi fails, use **Examples** only. They work offline.
5. Never show the terminal where you typed the token.

## The script

### 1. The problem (45 seconds)
Say: "A CI/CD pipeline is a program that runs automatically with real power: it can hold deploy keys, change the repository and run other people's code. Attackers know that a small edit to a workflow file, in a pull request that looks harmless, can give a pipeline new powers. Reviewers read the YAML diff, but it does not tell them what the change *makes possible*."

### 2. The idea (30 seconds)
Say: "PipeDelta compares the old and the new workflow and tells the reviewer, in plain sentences, what new powers the pipeline gained, with the exact line. It does not ask whether the file is bad. It asks what is new."

### 3. Live demo (3.5 minutes)
1. **Overview** (10 s): "These numbers come from the analyses I run. Nothing here is typed in."
2. **Analyze, GitHub repository** (30 s): connect `Vachana7/pipedelta`. "This is the real GitHub API."
3. **Pull request** (40 s): choose a pull request, Run analysis. Read the level aloud and the gate line: "this is what the GitHub check would decide".
4. **Open one finding** (40 s): "It tells me the job, step and line, the value before and after, why it matters and what to do." This is the strongest moment. Pause here.
5. **Compare tab** (25 s): "Left is old, right is new; the red dot is a finding."
6. **Jobs and steps** (20 s): "Here is each job's token access, secrets and outside addresses."
7. **Examples, "Outsider text passed between steps"** (40 s): "The line that changed looks harmless. The danger is a later step that pastes the pull request title into a command. A line-by-line diff would not show it."
8. **Download SARIF or Markdown** (15 s): "SARIF is the standard that GitHub code scanning reads."
9. **History** (10 s): "Everything is kept locally for review."

### 4. How it is built and tested (45 seconds)
Say: "Python engine, one dependency. The web app is a small standard-library server with a vanilla JavaScript interface, calling the same engine as the GitHub Action. 366 automated tests. The CI pipeline runs lint, types and tests on two Python versions, builds a Docker image, runs it against attack and safe examples, starts the web app inside the container and checks it, and runs PipeDelta on its own pull requests."

### 5. Honest results (45 seconds)
Say: "On 12 attack cases I reconstructed from public reports, it blocks 8, which is 8 of the 10 where a workflow file changes. That number is not independent, because I adjusted the tool to the misses. On 1,659 real past workflow commits from eight Python projects it would have blocked 159, about one in ten, mostly for unpinned actions. That is alert volume, not accuracy, because those commits are not labelled. So today it suits an advisory comment better than a strict gate."

## Questions experts are likely to ask

**How is it different from zizmor, actionlint or other scanners?**
"As far as I know, those tools analyse a workflow as it is, and report problems in it. PipeDelta reports what a *change* added, in plain sentences, with evidence. They can be used together. I have not compared them on the same cases, so I cannot say which finds more."

**Does it catch every attack?** "No. It reads workflow files only. It does not look inside the outside actions or scripts a workflow calls. It cannot see attacks that change no workflow file, such as a moved version tag. It misses addresses built from variables. It is meant to help a reviewer, not replace one."

**How do you know the levels are right?** "They are hand-written rules, measured two ways (docs/EVALUATION.md). The attack-case number is not independent. The history number measures alert volume, not accuracy."

**What are false positives and false negatives here?** "False positive: a High on a change that was fine, for example an unpinned action in a project that accepts that risk. False negatives are the attacks in the list of limits. I have not labelled the real-history alerts, so I cannot give a precision figure."

**What is "Inferred"?** "Findings from following outsider text through job and step outputs. The rules are tested on constructed cases. They have never fired on the real history, so I label them as inferred and do not claim they improve real-world detection."

**Why pull_request and not pull_request_target for your own workflow?** "A stranger's pull request then gets a read-only token and no secrets."

**Where is CI/CD in this project?** Two workflows: `ci.yml` (test, Docker build and checks, publish image on main) and `pipedelta.yml` (runs PipeDelta on this repository's own pull requests).

**Is the web app safe to run?** "It listens on localhost only, rejects other hosts and other websites, keeps the GitHub token in the server's environment only and never sends it to the browser, and refuses redirects away from api.github.com. It has no login, so it is for one person on one computer."

**What would you do next?** "Compare against zizmor on the same cases, label a sample of the blocked commits to measure precision, and test the sentences with real reviewers."

**Did you use AI?** Answer truthfully about how you used it, and say you can explain every module. Read `docs/LEARN.md` to be ready to explain `powers.py`, `delta.py` and `evidence.py`.

## If something goes wrong

| Problem | What to do |
|---|---|
| No internet or GitHub rate limit | Use Analyze, Examples (works offline). Say "this is the same engine on built-in workflows" |
| Server will not start | `pipedelta serve --port 8780` and open that address |
| Page blank | Check the server window is still open; Ctrl+Shift+R |
| Expert asks something you do not know | "I have not tested that. My guess is... and this is how I would check it." Never invent a number |

## Do not say
- "It stops all attacks" or "it is better than existing tools". Neither has been measured.
- "8 of 10 is the accuracy". It is a tuned result.
- Anything about performance improvements. None are claimed.
