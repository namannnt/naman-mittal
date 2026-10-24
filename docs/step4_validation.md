# Step 4: source-review handoff and portability

This handoff is for independent implementation review, not submission completion. No candidate personal answers, manual working, AI export, recording, remote, push, publication or form submission was created. Missing personal deliverables are explicit in README lines 1-3 and `candidate_completion_checklist.md`.

## Repository and dependency inspection

The baseline was clean `master` at `ada81aa` (report), following `a9152d1` (correctness review), `4825730` (validation), `be0595b` (implementation) and `cf39347` (audit). All 21 baseline tracked files were inspected by inventory/import/path searches. The handoff adds README, the checklist, this record and `analysis/validate_source_review.py`.

The complete runtime consists of `checker.py`, `quality_checker/__init__.py`, `quality_checker/core.py` and `quality_checker/config.py`. `requirements.txt` declares no third-party packages; AST inspection of every tracked Python file confirms only standard-library imports and this local package. The one dynamic Python import in the audit script is standard-library `sys`. Synthetic tests generate their fixtures themselves. There is no ignored fixture/helper, pip dependency, absolute machine path or fixed private-input location in checker/test/analysis source. Peer thresholds live in tracked configuration, not an untracked settings file. Detection logic, thresholds and reviewed CSVs were not changed in Step 4.

All analysis scripts are retained: pack audit, focused Step 2B evidence/sensitivity/provenance validation, report generation and optional print QA. `analysis/build_report.py`, `review_step2b.py` and `validate_step2b.py` intentionally contain supplied-snapshot station/date hypotheses; these are not imported by the general-purpose checker. Their import paths are derived from their own source location. `validate_step2b.py` regenerates root CSVs as part of its review; use a copy when reproducing that historical workflow. The report builder writes derived JSON under `tmp/`; it does not read a missing pre-generated figure or JSON helper.

Optional print QA needs Node, a Playwright module path and a browser executable supplied as arguments; Poppler is used to inspect/render its PDFs. Those local installations are machine-specific **QA tools**, not checker/test/runtime dependencies. This document records actual local paths below solely as execution evidence, not as portable configuration. The ignored original PDF, private extracted pack and print proofs are not review-bundle dependencies for running synthetic tests or opening the report. Supplied-data reproduction does require the private pack, intentionally provided separately.

## Actual clean-copy execution

The first fresh run archived committed baseline `ada81aa612f7bf16c9f71e04b1fb8614becaf113` with `git archive --format=zip`, verified archive members against `git ls-tree`, and extracted only those 21 tracked files into:

```text
C:\Users\dell\Desktop\bb bn\tmp\source review 5rcyz3bt\tracked copy
```

The pack remained separately at `C:\Users\dell\Desktop\bb bn\ridgeline_data_pack (2)`. No original checkout path was added to Python imports; `PYTHONPATH`/`PYTHONHOME` were removed for child processes. Import/tests and report build additionally used `-E -S` to ignore Python environment settings and site packages. Executable: `C:\Users\dell\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`, Python **3.12.14**, Windows. Python 3.11+ is the supported source target; this run did not test every supported Python version or another OS.

Actual commands, with `python` below denoting that exact executable and paths quoted as passed:

```text
# CWD: the clean tracked copy above
python -E -S -c "import quality_checker; from pathlib import Path; p=Path(quality_checker.__file__).resolve(); assert p.is_relative_to(Path.cwd()); print(p)"
python -E -S -m unittest discover -s tests -v
python checker.py "C:\Users\dell\Desktop\bb bn\ridgeline_data_pack (2)"
python -E -S analysis/build_report.py "C:\Users\dell\Desktop\bb bn\ridgeline_data_pack (2)"

# CWD: C:\Users\dell\Desktop\bb bn\tmp\source review 5rcyz3bt\alternate output with spaces
python "C:\Users\dell\Desktop\bb bn\tmp\source review 5rcyz3bt\tracked copy\checker.py" "C:\Users\dell\Desktop\bb bn\ridgeline_data_pack (2)"
```

The checker invocations use the documented one-argument command with the separate pack's absolute path substituted, rather than depending on its original relative folder location. Both the input path and clean/output paths contain spaces. Tests ran before supplied-pack output generation. The report build ran after both checker-output comparisons.

| Fresh observed result | Evidence |
|---|---|
| Package import | Resolved to the clean copy's `quality_checker/__init__.py`, not the original checkout. |
| Synthetic tests | **17 tests passed in 7.869 s**, exit 0; actual newly executed suite, not a repeated historical claim. |
| Clean-root command | Exit 0; wrote 15 flags and 22 diagnostics in that CWD. |
| Alternate-CWD command | Exit 0; wrote both files into the initially empty alternate output directory. |
| CSV preservation | Both generated files were byte-identical to the committed archive and working reviewed CSVs in both CWDs. |
| Dependency check | No third-party Python imports; no ignored helper was in the extracted tree. |
| Report reproduction | Exit 0; byte-identical rebuilt HTML with no external/generated-asset dependency. |
| Raw input preservation | All 19 file paths/hashes identical before/after; a separate comparison with Step 1's retained inventory also matched all 19. |

SHA-256 of reviewed and freshly reproduced files:

```text
flags.csv        b4c3fc3817e553c369e63b1e1f382056370ef0d0055ef10bd36373aaa301ba56
diagnostics.csv  5574c1b8e4516ae2f578c7c3b26279669c9a1ea89e20c6d799e07ceba275e071
report.html      45d133a4d095d33e0c6849f1d2ee1a2f42fc11cc798a419d879c4648b8cfbcd1
```

The new reproducibility script performs these archive/import/tests/two-CWD/byte/hash/report checks against **committed HEAD** and emits the full subprocess argv/results as JSON. Temporary clean copies are removed when the check exits. Run from the repository root after committing intended work:

```text
python analysis/validate_source_review.py "path with spaces/to/pack folder"
```

Git is required for this verification script only. Its output may be redirected into ignored `tmp/`; the first execution record is retained locally as `tmp/step4-baseline.json`. The initial baseline predates the new handoff files. Documentation-only changes do not justify detector changes. No material implementation failure was found.

### Complete committed handoff rerun

After inspecting/staging only the four handoff additions, genuine commit `27eda8ee594cd3dba4cec63d3b9852c0faf58a3f` was created. The same verifier was then executed again against that committed HEAD, now including **all 25 tracked files**, with full results retained locally in ignored `tmp/step4-handoff.json`. The clean copy was `tmp/source review 6o62w2vf/tracked copy` and the alternate CWD was its sibling `alternate output with spaces`; the separate input and interpreter paths were unchanged. Actual subprocess commands were those above with the new clean path substituted.

The fresh suite passed **17 tests in 7.791 s**. Package import, both CWD checker commands and the report rebuild all exited 0; both CSVs remained byte-identical at the hashes above, the report remained byte-identical and structurally self-contained, no third-party Python import was found, and all 19 inputs were unchanged. This checks the new handoff files as part of the archive rather than relying only on the pre-handoff baseline. A `git archive` ZIP of this commit was also checked against every tracked path and each committed file's bytes: all 25 matched, including the three `quality_checker` modules; ZIP integrity passed. The subsequent commit only adds this observed result to this document. The delivered ZIP is regenerated from final HEAD and checked again, not left at the earlier commit.

## Report handoff and prior print evidence

The unchanged HTML has embedded CSS and system fonts, no script/image/link/embedded-media dependency and no CSS imports/URLs. The clean-copy structural check and byte-identical rebuild were performed in Step 4. **No new visual verification or print rendering is claimed.**

Existing local evidence remains under ignored `tmp/report-render/`: colour/grayscale PDFs and PNGs, screen PNG and layout-check JSON. These were obtained in Step 3 by loading the exact HTML in offline headless Edge through the tracked Playwright QA script, printing A4 at 100% without browser headers/footers, inspecting `pdfinfo`/extracted text and visually reviewing 120-dpi colour/grayscale renders. Both final proofs were one A4 page, with all eight station rows/visit panel/footer present and no clipping/overflow. `docs/report_method.md` records the earlier failed render/overflow correction, settings, bounds and exact HTML hash. The proofs are retained locally, excluded from the archive as requested; a reviewer can reproduce them with their own local browser/tool paths. No missing generated figure is needed to open or regenerate the report.

## Bundle boundary and remaining blockers

After staged-content inspection and a genuine local handoff commit, create the review ZIP from committed tracked contents:

```text
git archive --format=zip --output=tmp/review_bundle.zip HEAD
```

`tmp/` is explicitly ignored, so the ZIP cannot recursively include itself. Archive member names/bytes must match the committed tree exactly; it contains the full package, tests, configuration, requirements, reviewed CSVs, report, README, analysis and documentation. It excludes `.git` (so it is not a development-history export), raw inputs/ZIP, assignment PDF, environments, caches, temporary print renders and credentials. The source bundle is not a copy of the private input pack and cannot replace candidate-owned deliverables or genuine AI logs.

No unresolved technical execution blocker was found on the tested Windows/Python setup. S04 temperature, S05 spatial identity, S07 onset/settings sensitivity and other documented scientific limits remain unresolved. Full name/email, personal DECISIONS/manual work, real AI exports, recording/link, deadline anchor, public repository/form details and the candidate's final checks are submission blockers. Nothing in this handoff asserts submission readiness.
