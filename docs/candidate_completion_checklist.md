# Candidate completion checklist

This is a handoff checklist, not a personal answer document, AI conversation export, recording or completed submission. No candidate identity has been inferred from local/Git usernames. Do not treat the source-review ZIP as a ready-to-submit repository.

## Codex-completed technical work

- [x] Audited the assignment/input structure and preserved input provenance/hashes; private assignment/data remain excluded from Git.
- [x] Implemented the general-purpose checker, complete importable package/configuration, standard-library dependency declaration and synthetic regression tests.
- [x] Reviewed correctness/recovery/provenance, recorded uncertainty and generated the reviewed `flags.csv` and supplementary `diagnostics.csv`.
- [x] Created the coordinator-facing offline report and documented the prior colour/grayscale A4 print verification.
- [x] Prepared README placeholders, this checklist and a reproducible clean tracked-copy portability check; results and source-review bundle details are in `step4_validation.md`.

## Candidate must complete personally

- [ ] Write root `DECISIONS.md` in your own words, **at most 1.5 pages**, ready to discuss it. The five required questions, without answers, are:
  1. Which one station should get the technician's one hour next week, exactly what should they do/check first, and why this station rather than the second-best?
  2. Which `flags.csv` decision is least certain, what is the evidence each way, and what single piece of information would settle it?
  3. What one or two plausible-but-wrong AI outputs occurred? Briefly quote them and explain how you noticed.
  4. For unattended operation at 500 stations next year, what would you change, drop, and refuse to automate?
  5. **Without code or AI**, roughly when in UTC is the sun highest at S04 on 20 March 2025? Show a few lines of your own working and explain its usefulness here.
- [ ] Complete that manual exercise independently. No solution, hints, derived time or verification is supplied here. If personal working is later added, it is outside Codex review scope: do not ask Codex to inspect/check/solve it.
- [ ] Make an approximately three-minute screen recording with your own voice. Open the actual data; show concrete evidence for the flag you are proudest of and the least-certain decision. Slides/editing are not required. Choose and explain the evidence yourself.
- [ ] Upload to unlisted YouTube or viewable Drive and test access without your signed-in privileges; put the working link in README line 3.
- [ ] Preserve complete, genuine, untidied AI conversations **from the first prompt onward**, including all sessions, mistakes, failed tests and dead ends, under `ai_logs/`. The brief accepts arrangements such as ChatGPT/Gemini share links or PDFs and Copilot chat JSON; retain full exports or files recording working share links. Do not substitute this checklist, selected snippets or reconstructed/fabricated transcripts for actual logs. Respect the assignment's private-data restriction when arranging access; do not upload the raw pack.
- [ ] Replace README lines 1-3 with verified full name, email and video link. Recheck line 4 on a fresh copy with the input pack supplied separately. Keep a record of any remaining limitations.
- [ ] Check the invitation/shared timestamp and timezone: the brief allows 48 hours after sharing and says later commits are not reviewed. No absolute deadline can be established from the repository alone.
- [ ] When authorised and within the assignment's sharing rules, create/confirm the **public GitHub repository named `firstname-lastname`**, retaining genuine incremental development history. Ensure root code, full package, `DECISIONS.md`, report, flags, README and `ai_logs/` are present. Never commit supplied raw ZIP/weather/GPS/stations/maintenance files, assignment PDF, secrets, environments or temporary proofs. The review archive has no `.git` history; do not use a single archive upload as a substitute for the existing history.
- [ ] Before the deadline, complete the [assignment submission form](https://docs.google.com/forms/d/e/1FAIpQLSdCsGD02h3RKokN4_Z-zMNzMwcV8eD8YtM56rXKXy8Bg4Gtsw/viewform?usp=sharing&ouid=101060328800031321516) with name, college, email, phone and repository link. Verify repository/video/log access. Publishing/pushing/submitting is not authorised in Step 4 and has not been done.

## Missing or unverified information/files at handoff

- Verified candidate full name and email; college and phone for the form.
- Candidate-authored `DECISIONS.md`, including independently completed manual working (not to be inspected by Codex).
- Own-voice recording and a working unlisted/viewable link.
- Complete genuine AI export/share-link files under `ai_logs/`, beginning at the first prompt. None has been manufactured.
- Invitation timestamp/timezone and confirmed absolute deadline.
- Correctly named public repository URL, visibility/access checks and form submission confirmation. The local repository currently has no configured remote.

The original raw ZIP was not supplied in this workspace, but the extracted 19-file pack is present separately; this is not a runtime blocker. Private inputs are intentionally absent from the source-review bundle, so an independent reviewer needs separately authorised access to the same-format pack for supplied-data reproduction; synthetic tests need no private pack. Scientific uncertainties in the README/report remain limitations, not resolved facts.
