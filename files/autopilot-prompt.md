You are implementing the PolicyPal project described in files/plan.md.

Work autonomously, but in controlled phase-sized increments.

Before changing anything:
1. Read files/plan.md and files/coding-standards.md, including the Git Workflow, Branching & Pull Request Strategy section.
2. Inspect the current workspace and git status. Confirm the working tree is clean and `main` is up to date.
3. Read IMPLEMENTATION_STATUS.md if it exists. If it does not exist, create it.
4. Identify the earliest incomplete implementation step in plan.md.
5. Create the branch declared for that step in plan.md: `git checkout main`, `git pull --rebase origin main`, then `git checkout -b <type>/<scope>-<summary>`. Never implement a step while on `main`.

Execution rules:
- Implement only the earliest incomplete step and other small prerequisite changes strictly required for it.
- Follow the architecture, technology choices, and folder structure in plan.md.
- Preserve existing user changes and do not revert unrelated work.
- Do not skip ahead to later phases.
- Do not create fake integrations or claim external services work without testing them.
- Keep secrets in environment variables.
- Keep domain code independent from frameworks and infrastructure.
- Add focused tests for every meaningful behavior.
- Prefer mock adapters and local services when real credentials or external services are unavailable.
- Use the existing project style and avoid unrelated refactoring.
- Keep each step on its own branch. One step, one branch, one pull request.

After implementation:
1. Run the narrowest relevant tests, type checks, linters, and syntax checks.
2. Fix failures caused by your changes.
3. Update IMPLEMENTATION_STATUS.md with:
   - completed step
   - files changed
   - validation commands and results
   - remaining limitations or blockers
   - the next recommended step
4. Review the final diff for accidental changes and confirm no secrets, `.env` files, or generated data are staged.
5. Commit using Conventional Commits: `<type>(<scope>): <imperative summary>`.
6. Push the branch with `git push -u origin <branch>`. Never push to `main`.
7. Open a pull request against `main` using the template that matches the branch type, apply the type and phase labels, link the issue, and describe what changed, why, and how it was validated.
8. Report the branch name and pull request link alongside the step summary.

Continue automatically through the remaining steps in the current phase only, opening a separate branch and pull request for each step. After the phase is complete and validated, stop and report:
- completed steps
- branches and pull requests opened
- files changed
- validation results
- blockers or risks
- the next phase

Stop immediately and report the blocker if:
- a required decision is missing from plan.md
- an external credential or service is required
- tests expose an architectural problem
- the implementation would require changing an earlier completed phase
- requirements conflict
- you cannot validate an important behavior

Never silently skip a failed test, security check, migration, or integration requirement.

Never commit directly to `main`, never force-push a shared branch, and never merge a pull request with failing checks.

Create/Use a python env for this project and only use that env instead of a global one.