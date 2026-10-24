# Assignment requirements

Source of truth: `Aeron-AI-Research-Engineer-Intern-AssignmentNew.pdf` (8 pages). The supplied data README is used only for pack-format facts. This document separates requirements stated in the brief from implementation notes for later work.

## Required deliverables and checker contract

- Submit a checker, a network health report, `DECISIONS.md`, the resulting `flags.csv`, a short `README.md`, complete `ai_logs/`, and a three-minute recording in a public GitHub repository.
- The checker reads the data-pack folder supplied as its single command-line argument.
- It must run with one command and write `flags.csv` into the directory from which the command is run, not into the pack.
- It must work on another, unseen pack in the same format.
- `flags.csv` has one row per problem the candidate judges to be real, with exactly the described fields:

| Column | Required meaning / allowed values |
|---|---|
| `station_id` | Station identifier, e.g. `S03`. |
| `channel` | A data column name such as `temp_c`, or `all`, or `metadata`. |
| `start_utc`, `end_utc` | Start and end, formatted `YYYY-MM-DD HH:MM`. |
| `issue` | A few words. |
| `action` | `exclude`, `correct`, or `keep`; `keep` means it looks odd but is real. |
| `note` | One sentence of evidence; if the action is `correct`, state how. |

- Any programming language and any free libraries may be used. Only free tools are allowed.
- The supplied pack says weather logger timestamps use `YYYY-MM-DD HH:MM`, represent the end of each interval, and are meant to be UTC. It describes a nominal 10-minute interval and the channels `temp_c`, `rh_pct`, `pressure_hpa`, `wind_kmh`, `wind_dir_deg`, `rain_mm`, and `ghi_wm2`.
- Do not commit the data pack.

## Report

- Create `report.html` or `report.pdf` at the repository root.
- The brief calls it a "one-page network health report" but explicitly permits "two pages at most".
- It must be printable on A4, written for the non-technical network coordinator, answer which data is good enough for the spring climate summary and where to send the one technician, and show only what the coordinator needs to act.
- Appearance, readability, judgement, and evidence matter; a generic first-pass AI-looking report counts against the submission.

## `DECISIONS.md`

- At most 1.5 pages and in the candidate's own words. AI may be used for code, but the candidate must write this document and be ready to discuss it.
- Answer all five prompts:
  1. Choose one station for a one-hour technician visit next week; say exactly what to do and check first, and why it beats the second-best station.
  2. Choose the least-certain `flags.csv` decision; give evidence on both sides and the single fact that would settle it.
  3. Give one or two moments when AI produced something plausible but wrong; quote briefly and explain how it was detected.
  4. Explain what to change or drop, and what not to automate, if the checker runs unattended on 500 stations next year.
  5. Without code or AI, estimate when the sun is highest at S04 on 20 March 2025 UTC; show a few lines of working and explain its relevance.

This Step 1 audit intentionally does not create `DECISIONS.md` and does not solve prompt 5.

## README, repository, AI log, recording, and form

- The public GitHub repository name must be `firstname-lastname` (example: `asha-kulkarni`).
- At the repository root, include the code, `DECISIONS.md`, the report, the pack's `flags.csv`, and a short `README.md` explaining how to run it, what each check does, and what was not completed.
- The README must start with these four lines, in this order: the candidate's full name; the candidate's email; the video link; `Run: <your one command>`.
- Commit as work progresses; reviewers want the development history, not one upload at the end.
- Add `ai_logs/` containing complete, untidied exports of AI chats from the first prompt onward, including dead ends (examples in the brief include share links/PDFs and Copilot chat JSON).
- Provide a three-minute screen recording with the candidate's voice, linked as an unlisted YouTube or Drive video in the README. Open the data and show evidence for the proudest flag and the least-certain flag. Slides and editing are not required.
- Before the deadline, fill in the linked submission form with name, college, email, phone, and repository link.

## Deadline, ambiguity, and data restrictions

- Exact deadline wording: "48 hours after this assignment is shared with you."
- Exact enforcement wording: "Commits after the deadline are not looked at."
- Ambiguity: the PDF does not include an absolute timestamp or state what event/system proves when it was "shared"; the candidate should retain the invitation timestamp and use its timezone as the deadline anchor.
- Expected effort is "About 10-12 hours"; this is not the deadline.
- The pack is for this assignment only. Do not commit or share it, and do not share the solution before the deadline.
- If the brief is ambiguous, make a sensible assumption and record it.

## Implementation notes for the next step (not brief requirements)

- Keep the checker deterministic, pack-agnostic, and dependency-light; derive station IDs, dates, interval, and row counts from inputs.
- Preserve source row position and raw timestamp text so clock resets and collisions remain auditable.
- Treat quality findings independently by channel and time range; invalid GPS evidence should not automatically invalidate weather observations.
- Emit stable, documented evidence summaries and tests before producing the final `flags.csv`.
