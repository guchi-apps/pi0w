# Pi Zero W development rules

- Use develop for integration and main for approved formal releases. Work on issue-<number> branches and open PRs; do not push application changes directly to protected branches.
- Honor IssueDeck's configured Claude/Codex provider and model. Planning, implementation, review, repair, integration verification and release use the shared workflow/dispatcher.
- Run agents and tests on the subPC or GitHub-hosted runners. BLE collection stays on the Pi. Do not install AI agents, Node or heavy build tools on the Pi.
- Preserve ARMv6 and Python 3.7 compatibility. Offline tests do not prove BLE/GPIO/I2C compatibility.
- Verification: python3 -m pip install -r requirements-ci.txt && bash scripts/verify.sh
- Secrets, .env, sensors.json, SSH keys and runtime history remain private. Never put them in code, Issues, logs or release assets.
- .shared-context/ is read-only. Store repository-specific knowledge in docs/.
- Main/release publication and successful hardware deployment are separate states. Leave an Issue open when runtime verification or manual setup remains.
- Deploy only formal releases through the existing subPC controller. Preserve live configuration and history; use verified SSH trust and rollback on failure.
