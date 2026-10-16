# IssueDeck integration

Shared callers are pinned to workflows/v52. Supported operations: planning/implementation, issue progress, code review, CI repair, review repair, conflict resolution, PR repair, version checks and develop-to-main release preparation.

GitHub-hosted offline CI uses Python 3.7/3.11. The subPC uses the generic IssueDeck launcher; repository registration and release deployment timer have already been configured. Full review, integration verification and planning review use the application's dispatcher settings. Mac/Xcode verification is not applicable.

Privileged callers first check the originating repository and actor's write permission. Fork PRs only receive ordinary offline CI. Shared prompts and source code are never executed on the Pi.

## Account configuration

Set default branch to develop and protect main/develop with PR and CI requirements. Grant the existing IssueDeck GitHub App access to this repository and provide the existing organization Secrets required by the shared workflows. Required names are reported by the onboarding check without exposing values. No new credentials are committed.

In IssueDeck, synchronize repositories first, then Issues. Verify a read-only question before starting an implementation and follow its plan, PR, review, repair and release progress. Bootstrap alone is not end-to-end verification.

Use version.json and scripts/bump_version.py for release versions. Publish verified source assets from main. The Pi controller polls only formal Release assets and records successful deployment separately.

## Operation order

Follow this order for each Issue. Do not skip ahead; a missing earlier step is a blocker.

1. Repository resync: synchronize repositories in IssueDeck so the latest repository state and settings are reflected.
2. Issue resync: synchronize Issues so the board shows the current Issue body, labels and comments.
3. Plan / implementation: record a plan (small changes may record it and proceed), then implement on an `issue-<number>` branch.
4. PR / review: open a PR against develop and hand over to the existing CI and automated review. Repair CI or review findings through the shared workflows.
5. Formal Release: prepare develop-to-main release with version.json and scripts/bump_version.py, then publish verified source assets from main. Only formal Release assets are deployed to the Pi.

Main/release publication and hardware deployment success are separate states; leave the Issue open while runtime verification or manual setup remains.

## Release caller (candidate / finalize)

The release caller accepts `candidate_request` and `finalize_request` (workflow_dispatch string inputs, empty by default) and passes them as `candidate-request` / `finalize-request`, so IssueDeck can start "create and verify candidate" then finalize. Adopted shared tag: `workflows/v52` (published; contains the candidate/finalize inputs, absent in v50, and the IssueDeck#4650 fix that stops a develop sync push from starting a legacy bump, absent in v51). The tag number alone is not the evidence; re-check these two points when changing the tag. `version.json` is the only version file (no changelog or iOS version to sync); `scripts/bump_version.py` accepts the same version again so a finalize retry does not double-bump, and rejects a lower one.

Rollout records are kept separately: develop caller merge (this PR), main caller reflection, and the end-to-end run (candidate, finalize, main, deploy, sync PR, next candidate). Only the first is covered by this change; the others need a human-approved real release and are tracked in IssueDeck#4651. Until main has the new caller, the old flow runs and nothing is published without the existing approval.

## Remaining validation

Account/default-branch settings, branch protections, App/Secrets reachability, board synchronization and a representative end-to-end Issue must be verified. Missing settings are blockers, not successful operation.
