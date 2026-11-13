# UX research and design

This covers the user-experience part of the course: who the tool is for, what
their day looks like, and how the report was designed for them.

These personas and the journey are **assumptions** based on public write-ups
of pipeline attacks and on how pull request review works on GitHub. Nobody was
interviewed. Testing the report with real reviewers is listed as future work.

## Who it is for

### Persona 1: Meera, volunteer maintainer

- Maintains a small open-source Python library in her spare time, about four hours a week.
- Reviews pull requests from people she has never met.
- Knows Python well. Knows GitHub Actions only as far as "copy a working file and adjust it".
- Goal: merge helpful contributions quickly without breaking anything.
- Worry: approving something she did not fully understand.
- Quote that sums her up: "If the tests are green and the change is small, I merge."

### Persona 2: Arjun, platform engineer at a mid-size company

- Owns the pipelines of about sixty repositories.
- Gets ten or more pipeline changes a week from product teams.
- Knows GitHub Actions deeply, but has little time per change.
- Goal: spot the two changes a month that need a real security look.
- Worry: alert fatigue. He has already muted two scanners because they flagged everything.
- Quote: "Tell me what changed. Do not tell me everything that is wrong with the file."

Arjun's quote is the design brief. It is why PipeDelta reports only what a
change added, and why the evaluation measures how often it interrupts.

## User journey: reviewing a pipeline change

| Step | What Meera does today | What she feels | With PipeDelta |
|---|---|---|---|
| 1. Notification | Gets an email: "Add formatting workflow" | Neutral. Looks routine. | Same |
| 2. Opens the pull request | Sees 14 new lines of YAML | Slight unease. She does not read YAML fluently. | Sees a comment at the top: "This change gives the pipeline 5 new powers. Highest level: high." |
| 3. Reads the change | Skims. Recognises `checkout`. Does not know what `pull_request_target` means. | Tempted to trust it. | Reads five sentences in plain English, each naming one power |
| 4. Decides | Tests are green, so she approves | Mild doubt, quickly forgotten | Sees "can now read the secret DEPLOY_TOKEN" and "a command now contacts collector.example.invalid". Asks the author why. |
| 5. Afterwards | Weeks later, finds her publishing key was used by someone else | Alarm, guilt | The question in step 4 is never answered, and she closes the pull request |

The moment that matters is step 3. The design goal is to move the reviewer
from "tempted to trust it" to "has something specific to ask".

## Design decisions that came from this

| Decision | Reason |
|---|---|
| Report only powers that are new | Arjun mutes tools that repeat old problems on every change |
| One sentence per power, no jargon where avoidable | Meera does not know what `pull_request_target` is; the sentence says what it allows |
| One comment that updates itself | A stack of comments hides the current state |
| Levels shown as words, with high listed first | She may read only the first two rows |
| A closing line saying a person should still review | The tool must not create false confidence |
| `fail-on: never` option | The evaluation showed about one change in ten is blocked; some teams will want advice without a gate |

## Wireframes

### Pull request comment (the main screen)

    +--------------------------------------------------------------+
    | PipeDelta report                                             |
    |                                                              |
    | This change gives the pipeline 5 new powers.                 |
    | Highest level: high.                                         |
    |                                                              |
    | .github/workflows/format.yml                                 |
    | +--------+-------------------------------------------------+ |
    | | Level  | New power                                       | |
    | +--------+-------------------------------------------------+ |
    | | high   | A command now contacts <address>. The same job  | |
    | |        | can read secrets, so they could be sent there.  | |
    | | high   | Now runs on 'pull_request_target', which people | |
    | |        | outside the project can set off ...             | |
    | | medium | Can now read the secret <NAME>.                 | |
    | | low    | Now runs GitHub's own action <name>.            | |
    | +--------+-------------------------------------------------+ |
    |                                                              |
    | PipeDelta reads workflow files only ... A person should      |
    | still review this change.                                    |
    +--------------------------------------------------------------+

### Results page (`dashboard/index.html`)

    +--------------------------------------------------------------+
    | PipeDelta                                                    |
    | One-sentence description                                     |
    |                                                              |
    | +---------------------------+------------------------------+ |
    | | The change (new lines     | What PipeDelta reports       | |
    | | highlighted)              | (the sentences)              | |
    | +---------------------------+------------------------------+ |
    |                                                              |
    | How well does it work?                                       |
    | [ 6 of 10 ]   [ 8 of 10 ]   [ 9.9% ]                         |
    |                                                              |
    | Test 1: table of attack cases, blocked / missed / cannot see |
    | Test 2: one bar per project, split by level                  |
    | What it cannot do: list                                      |
    +--------------------------------------------------------------+

The first thing on the page is the tool's real output next to the change that
caused it, because that is the whole idea in one view.

## Figma prototype

Make a three-frame click-through in Figma from the wireframes above:

1. Pull request page with the red PipeDelta check and the comment (use a screenshot of pull request #2 as the reference).
2. The same page after the fix, with fewer rows in the comment.
3. The results page.

Link frame 1 to frame 2 with a click on "Commit changes", and add a link from the comment to frame 3.
Put the share link here when it is done: (link)

## Usability checks done

- The results page was checked at desktop and phone width.
- Colours in the chart were checked with a colour-blindness validator, in light and dark mode.
- Status is always written as a word (blocked, missed, high), never shown by colour alone.
- The chart has the same numbers available as a table.

## Not done

- No interviews or usability tests with real reviewers.
- No measurement of whether the sentences change what reviewers decide.
