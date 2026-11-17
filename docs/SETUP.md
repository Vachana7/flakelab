# Setting up and running PipeDelta (Windows first)

This guide takes you from nothing to a running PipeDelta web app on a Windows
laptop. Commands marked **PowerShell** are for Windows PowerShell or the
PowerShell terminal in VS Code. Commands marked **Linux/macOS** are only for
those systems. Everything below was checked against the `platform` branch.
The commands were run on Linux; the Windows commands are standard PowerShell
and were not run on a Windows machine here, so follow the troubleshooting
section if one differs.

Everything runs on your own computer. The web app listens on `127.0.0.1` only
(your laptop, not the network). The GitHub token, if you use one, stays in the
terminal that starts the server.

---

## A. Get the project

1. **Open the repository.** In Chrome go to <https://github.com/Vachana7/pipedelta>.
2. **Install Git** if `git --version` in PowerShell is not recognised: <https://git-scm.com/download/win> (accept the defaults).
3. **Clone it.** In PowerShell, in the folder where you keep projects:

   ```powershell
   cd $HOME\Documents
   git clone https://github.com/Vachana7/pipedelta.git
   cd pipedelta
   ```
   This copies the code into a new `pipedelta` folder. Cloning a public repository needs no login.
4. **Switch to the `platform` branch** (it holds the web app):

   ```powershell
   git checkout platform
   git branch --show-current
   ```
   Expected output of the second command: `platform`.
5. **Open it in VS Code.** From the same folder:

   ```powershell
   code .
   ```
   (If `code` is not recognised, open VS Code, choose File, Open Folder, and pick the `pipedelta` folder.) Open the terminal inside VS Code with Ctrl+` and keep using PowerShell.

## B. Set up Python

1. **Python version:** 3.10 or newer (the project is tested on 3.10 and 3.12). Check:

   ```powershell
   python --version
   ```
   Expected: `Python 3.12.x` (any 3.10 or newer is fine). If it is missing or older, install Python from <https://www.python.org/downloads/> and **tick "Add python.exe to PATH"** on the first screen. Then close and reopen the terminal.
2. **Software needed:** Python and Git. The only Python package it installs is `pyyaml` (PyYAML 6 or newer), which `pip` fetches for you. You do **not** need Node.js, a build step, or Docker to run the web app.
3. **Create a virtual environment** (a private copy of Python for this project), in the `pipedelta` folder:

   ```powershell
   python -m venv .venv
   ```
   This creates a `.venv` folder (it is already in `.gitignore`).
4. **Activate it in PowerShell:**

   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   Your prompt now starts with `(.venv)`. You must do this in every new terminal before running PipeDelta.
5. **Install the project and its dependency:**

   ```powershell
   python -m pip install --upgrade pip
   pip install -e .
   ```
   `-e .` installs the folder you are in so the `pipedelta` command exists. Expected: a final line beginning `Successfully installed` that includes `pipedelta-0.5.0` and `pyyaml`.
6. **Verify the installation:**

   ```powershell
   pipedelta --help
   ```
   Expected: a usage line `usage: pipedelta [-h] {diff,git,action,serve} ...` listing `serve`. Optional: run the project's own tests (this needs `pip install pytest` once):

   ```powershell
   pip install pytest
   python -m pytest -q
   ```
   Expected: `366 passed`.

**Linux/macOS** equivalent of steps 3 to 5:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## C. GitHub authentication

1. **Is a token required?** No. Without a token PipeDelta can read **public** repositories, limited by GitHub to 60 requests per hour. A token raises that to 5,000 per hour and lets you read **private** repositories you can access. The built-in examples and the "Paste a workflow" tab need no token and no internet.
2. **Create a read-only token.** On GitHub: your profile picture, Settings, Developer settings, Personal access tokens, **Fine-grained tokens**, Generate new token.
   - Name: `pipedelta-readonly`. Expiration: a few days is enough.
   - Repository access: **Only select repositories**, and choose the repositories you will analyse.
   - Permissions, Repository permissions: **Contents: Read-only** and **Pull requests: Read-only**. (Metadata read-only is added automatically.) Give it nothing else, no write access.
   - Generate, and copy the token (it starts with `github_pat_`). GitHub shows it only once.
3. **Configure it in PowerShell without typing it where it can be seen.** This prompts for the token with hidden input and keeps it only in this terminal window:

   ```powershell
   $t = Read-Host "GitHub token" -AsSecureString
   $env:GITHUB_TOKEN = [System.Net.NetworkCredential]::new("", $t).Password
   ```
   PipeDelta reads the first of `PIPEDELTA_GITHUB_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN` that is set. The value disappears when you close the window. Do not put it in a file in the project, in `setx`, or in a command you paste into chat.
4. **Verify connectivity** after the server is running (section D), in a second PowerShell window:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/api/session
   ```
   Expected with a good token: `github.token_set` is `True` and `github.user` is your GitHub user name, with a `rate` showing a limit of 5000. Without a token, `token_set` is `False`. The token itself is never shown.
5. **Keeping it out of sight:**
   - Never paste the token into the web page, a screenshot, a slide, a commit or a chat. The app has no field for it.
   - The server never prints it, and no API response contains it (this is tested). The side bar shows only your user name and the remaining request count.
   - When you screenshot a terminal, do not include the `Read-Host` line's reply. Close the window after the expo and revoke the token on GitHub (Settings, Developer settings) if you shared your screen.

## D. Run PipeDelta

PipeDelta is **one process**: the same command starts the backend API and serves the front end. There is no separate frontend to start.

1. **Start it** (virtual environment active, token set if you want one):

   ```powershell
   pipedelta serve
   ```
   Expected output:

   ```
   PipeDelta 0.5.0 is running at http://127.0.0.1:8765
   GitHub token: set.  History: pipedelta.db.  Press Ctrl+C to stop.
   ```
   (`not set (public repositories only, 60 requests/hour)` appears if there is no token.) Leave this window open. Options: `--port 8780` to use another port, `--db path` to keep history elsewhere. History is saved in `pipedelta.db` in the folder you started from. The server refuses to answer anything but `localhost`, `127.0.0.1` and `[::1]`; do not change `--host`.
2. **Open it in Chrome:**

   ```powershell
   start chrome http://127.0.0.1:8765
   ```
   or type the address into Chrome yourself.
3. **Check the health endpoint** in a second PowerShell window:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/api/health
   ```
   Expected: `ok True` and `version 0.5.0` (the raw reply is `{"ok": true, "version": "0.5.0"}`).
4. **Stop it safely:** click the server window and press **Ctrl+C**. Expected: `Stopped.` The history stays in `pipedelta.db`. Then `deactivate` leaves the virtual environment.

**Linux/macOS:** the same `pipedelta serve`; for the token use `export GITHUB_TOKEN=...` (typed with a leading space or read with `read -s` so it stays out of your shell history), health check `curl http://127.0.0.1:8765/api/health`.

## E. Using the application

1. **Connect a repository.** Click **Analyze**, stay on the **GitHub repository** tab, type `Vachana7/pipedelta` (or a full `https://github.com/...` address), and click **Connect**. You see the repository and its workflow files. It is also remembered under **Repositories**.
2. **Select a pull request.** Under "Choose what to analyze" click **Pull request** and pick one from the list of open pull requests. The other choices are **Latest change** (a file's newest commit against the one before) and **Current file** (what the file can do today).
3. **Run the analysis.** Click **Run analysis**. The result page opens with the overall risk level and whether the GitHub Action's default gate would fail.
4. **Understand the findings.** Each finding is a new power the change gives the pipeline. **High** means the change makes a harmful combination possible (for example a secret beside an outside address); **Medium** and **Low** are smaller. The tag at the right says how sure PipeDelta is: *Written in file* (the file says it directly), *Inferred* (worked out by following where text flows), *File is silent* (unknown). Powers that were removed or made safer are listed separately and never raise the level. PipeDelta reports what a change makes possible, not that an attack happened.
5. **Explore the evidence.** Click any finding. The panel shows where it is (file, job, step, line), what changed (before and after values), the lines from the file with the relevant one highlighted, why it matters, and what to do. Press Esc to close.
6. **See the before/after comparison.** Open the **Compare** tab: old file on the left, new file on the right, changed lines coloured, and a red dot on any line that has a finding (click it to open the evidence).
7. **Check jobs and steps.** Open **Jobs and steps**: each job with its runner, token access, secrets, outside addresses, unpinned actions and whether it uses outsider-written text, and its steps in order with flagged steps highlighted. **Attack paths** lists dangerous pairings inside one job and whether this change made them possible.
8. **Download reports.** Click **Download report** and choose Markdown (to paste into a ticket), HTML (one file, prints well), JSON (the full result) or SARIF (the format GitHub code scanning reads).
9. **View history.** **History** lists every analysis, newest first, with a filter box. Click one to reopen it. **Overview** shows totals and charts computed from that history.

No GitHub repository handy? **Analyze, Examples** runs five built-in workflows with no internet.

## F. Troubleshooting

| Problem | Fix |
|---|---|
| `python` is not recognised | Install Python from python.org with "Add python.exe to PATH" ticked, reopen the terminal. Or try `py --version` and use `py -3.12 -m venv .venv`. Windows may also open the Microsoft Store: turn off the "python.exe" app alias in Settings, Apps, Advanced app settings, App execution aliases. |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | Run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again. Or use Command Prompt: `.venv\Scripts\activate.bat`. |
| `pipedelta` is not recognised | The virtual environment is not active (no `(.venv)` in the prompt). Activate it. Or run `python -m pipedelta serve`. |
| `ModuleNotFoundError: No module named 'yaml'` (or `pipedelta`) | Activate `.venv`, then `pip install -e .` again from the `pipedelta` folder. |
| Port 8765 already in use (`OSError ... Address already in use` / error 10048) | Start on another port: `pipedelta serve --port 8780` and open that address. Or find the old one: `netstat -ano | findstr :8765`, then `taskkill /PID <number> /F`. |
| Invalid GitHub token (the page says "GitHub did not accept the token set on the server") | The token is wrong, expired or revoked. Stop the server (Ctrl+C), set a new token as in section C, and start again. To go without a token, close the window and start in a fresh one. |
| GitHub rate limit ("GitHub rate limit reached") | Without a token the limit is 60 requests per hour. Set a token (section C), or use the built-in examples and the paste tab, which need no GitHub. The side bar shows the requests left. |
| "Repository not found" or "GitHub refused access" | Check the spelling. A private repository needs a token that was given that repository. Note that with some tokens a missing repository also reports "refused access". |
| Backend does not start | Read the last lines of the error. Check `python --version` is 3.10 or newer and that `pipedelta --help` works. Make sure you are in the `pipedelta` folder on the `platform` branch (`git branch --show-current`). |
| Page does not load or looks blank | The server must still be running (health check in section D). Use `http://127.0.0.1:8765` exactly, not another computer's name (other host names are refused on purpose). Hard-refresh with Ctrl+Shift+R. Press F12, Console, to see an error. |
| "Cannot reach the PipeDelta server" banner | The server window was closed or stopped. Start it again. |
| Docker unavailable | You do not need Docker for the web app. Docker is only for the offline command-line backup (`docker compose run --rm attack`, see `docs/DEMO.md`) and for the CI. Install Docker Desktop and start it, or skip those steps. |
| Could not reach GitHub (network) | Check the internet connection and any proxy. The examples still work offline. |

---

## G. Expo quick start (about 4 minutes)

Before the day: do sections A and B once on the laptop, create the token (C.2), and run `pipedelta serve` once with internet to confirm it works. On the day:

```powershell
cd $HOME\Documents\pipedelta
.\.venv\Scripts\Activate.ps1
$t = Read-Host "GitHub token" -AsSecureString
$env:GITHUB_TOKEN = [System.Net.NetworkCredential]::new("", $t).Password
pipedelta serve
start chrome http://127.0.0.1:8765
```

Then:

1. **(20 s) The idea.** "When someone changes a pipeline, PipeDelta tells the reviewer what new powers it gained, and shows the line." Point at Overview.
2. **(30 s) Connect.** Analyze, type `Vachana7/pipedelta`, Connect. It lists the real workflow files.
3. **(60 s) A real pull request.** Choose **Pull request**, pick the open pull request, Run analysis. Say the level and what the gate would do. Open one finding: the line, before and after, the advice.
4. **(40 s) Compare and structure.** Compare tab: changed lines with red dots. Jobs and steps: which job holds which secret and token.
5. **(40 s) The subtle case.** Analyze, Examples, "Outsider text passed between steps". Show that the edited line looks harmless but a later step pastes the pull request title into a command. Works with no internet.
6. **(30 s) Report.** Download report, SARIF (or Markdown) and open it.
7. **(20 s) History.** Open History and Overview: the numbers are the runs you just made.

If the Wi-Fi fails: skip steps 2 and 3 and use **Examples** only, or the Docker backup in `docs/DEMO.md`. Say the limits out loud: it reads workflow files only, and "inferred" findings come from rules that have been tested but have not fired on real history. Stop with Ctrl+C when finished.
