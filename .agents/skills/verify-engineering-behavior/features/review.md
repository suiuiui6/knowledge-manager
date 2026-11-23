# Review and publish

## Sub-features

Approve a draft, retry without duplicate effects, search the published module. Multiple distinct reviewers and content-version invalidation are covered in CLI/HTTP and storage regressions.

## How to get to it (user POV)

Initialize a KB, add a draft to staging, then use `km review approve MODULE_ID` and `km search QUERY` with the same --kb-path.

## Driving it with the helper

Run the skill command. It seeds a valid local draft without an LLM, invokes the real CLI twice, compares the saved module and searches the title. The fixture is a precondition, not a claim of extraction coverage.

## Gotchas

The helper verifies a single-reviewer threshold. Multi-reviewer and HTTP paths require the additional tests listed in the skill. Interactive review must bind approval/discard to the content version and review round shown before waiting for input. Run `tests/test_cli.py -k interactive_review_refuses_changed_displayed_draft` to verify edits and resubmission during the prompt are rejected; the helper itself does not drive that prompt race. Local Git reviewer resolution may fall back to a local label; it does not simulate different reviewers.
