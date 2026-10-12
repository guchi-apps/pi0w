# IssueDeck integration

Shared callers are pinned to workflows/v50. Supported operations: planning/implementation, issue progress, code review, CI repair, review repair, conflict resolution, PR repair, version checks and develop-to-main release preparation.

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

## Remaining validation

Account/default-branch settings, branch protections, App/Secrets reachability, board synchronization and a representative end-to-end Issue must be verified. Missing settings are blockers, not successful operation.
