# Implementation Status

Tracks progress against `files/plan.md`, per the process defined in
`files/autopilot-prompt.md`. Updated after every completed step.

## Phase 0 — Git Repository & Delivery Workflow

### Step 0.1 — Initialize the repository and trunk — DONE

- Files: `.gitignore`, `.gitattributes`, `files/*.md` (bootstrap commit on
  `main` directly — the one exception to "never commit to main", since `main`
  didn't exist yet to branch from).
- Validation: `git push -u origin main` succeeded;
  `gh repo view --json defaultBranchRef` confirms `main` is the default
  branch.
- No PR for this step (bootstrapping paradox — see note above).

### Step 0.2 — Branch protection and ownership — DONE

- Files: `.github/CODEOWNERS`.
- Branch: `chore/branch-protection-and-codeowners` → PR #1 (squash-merged).
- Branch protection applied to `main` via `gh api`:
  `required_approving_review_count: 0` (solo-maintainer adjustment — GitHub
  disallows self-approval and there is no second reviewer yet),
  `require_code_owner_reviews: false` (same reason), `enforce_admins: true`,
  `required_linear_history: true`, `allow_force_pushes: false`,
  `allow_deletions: false`, `required_conversation_resolution: true`,
  `required_signatures: true`.
- Repo settings: squash-merge only (`mergeCommitAllowed`/`rebaseMergeAllowed`
  = false), `deleteBranchOnMerge: true`.
- Commit signing set up: SSH-based (`gpg.format=ssh`), local (non-global) git
  config, key registered via `gh ssh-key add --type signing`.
- Validation: `gh api repos/.../branches/main/protection` response confirmed
  all fields; `gh repo view --json deleteBranchOnMerge,squashMergeAllowed,...`
  confirmed merge settings.
- Known limitation: two-approval enforcement for CODEOWNERS paths (auth,
  tenant middleware, persistence adapters, migrations) is documented but not
  enforced (`required_approving_review_count: 0`) because this is a
  solo-maintained repo. Raise to 2 for those paths when a collaborator joins.

### Step 0.3 — Commit, branch, and PR conventions — DONE

- Files added: `commitlint.config.js`, `.pre-commit-config.yaml`,
  `.github/pull_request_template.md`,
  `.github/PULL_REQUEST_TEMPLATE/{feature,bugfix,refactor,chore,security,docs}.md`,
  `.github/ISSUE_TEMPLATE/{bug_report,feature_request,config.yml}`,
  `.github/labeler.yml`, `CONTRIBUTING.md`, this file.
- Branch: `chore/commit-and-pr-conventions`.
- Labels created on GitHub: `type: feature`, `type: bug`, `type: hotfix`,
  `type: refactor`, `type: docs`, `type: chore`, `type: security`,
  `area: backend`, `area: frontend`, `area: infra`, `area: data`,
  `phase-0` … `phase-14`.
- Validation: `.pre-commit-config.yaml` and `commitlint.config.js` are config
  only at this point — `pre-commit` is not yet installed since no Python
  venv or backend/frontend code exists yet to lint. Both will be exercised
  for real starting Phase 1 once `backend/` and `frontend/` exist.

### Step 0.4 — Continuous integration pipelines — DONE

- Files: `.github/workflows/{ci,pr-lint,secret-scan,dependency-audit,docker-build,migration-check,release}.yml`.
- Branch: `ci/core-pipelines`.
- `ci.yml` has `backend-quality` and `frontend-quality` jobs; both guard on
  `backend/pyproject.toml` / `frontend/package.json` existing and no-op
  cleanly until Phase 1 / Phase 10 add real code, so PRs aren't blocked by
  checks for code that doesn't exist yet.
- `docker-build.yml` and `migration-check.yml` guard the same way on
  `backend/Dockerfile`/`frontend/Dockerfile` and `backend/alembic.ini`.
- `pr-lint.yml` validates the PR title (Conventional Commits) and branch name
  (`<type>/<scope>-<summary>`) against the same rules as `commitlint.config.js`
  and `CONTRIBUTING.md`.
- `secret-scan.yml` runs `gitleaks/gitleaks-action@v2` on every PR and push.
- `dependency-audit.yml` runs `pip-audit`/`npm audit`, guarded the same way,
  plus a weekly schedule.
- `release.yml` uses `googleapis/release-please-action@v4` (release-type
  `simple`) to derive the next semver from merged Conventional Commit types,
  generate `CHANGELOG.md`, and cut a GitHub Release with a tag on merge of
  its auto-generated release PR.
- **Known limitation**: tags/commits created by `release-please-action`
  (via `GITHUB_TOKEN`) are GitHub-API-created, not cryptographically signed
  with the SSH key set up in Step 0.2. They'll show as GitHub-verified
  (web-flow) but not "signed by rohangawhade's key." Getting true user/bot-key
  signed release tags out of Actions needs a dedicated bot signing key stored
  as a repo secret — deferred; flagging here rather than silently skipping it.
- Once this PR is open, its own checks (`pr-lint`, `secret-scan`,
  `dependency-audit`, `ci`, `docker-build`, `migration-check`) are the first
  real run of all seven workflows. After they pass, required status checks
  will be added to `main`'s branch protection to match.

**Phase 0 — Git Repository & Delivery Workflow: COMPLETE** (pending this PR's
merge).

## Environment / tooling notes for future steps

- **gh CLI**: installed via `winget install --id GitHub.cli`, authenticated
  as `rohangawhade` (scopes: `repo`, `read:org`, `gist`,
  `admin:ssh_signing_key`). `gh.exe` is copied to `~/bin/gh.exe` (already on
  Git Bash's `PATH`) so commands can be invoked as plain `gh ...` — this
  matters because the `gh pr merge`/`gh pr close` permission rule only
  matches commands that literally start with that text.
- **PR merges**: the auto-mode classifier hard-blocks `gh pr merge`/
  `gh pr close` by default and blocks any attempt to self-modify
  `.claude/settings.*` permissions. The user added an explicit allow rule to
  `.claude/settings.local.json`. Per-PR: I still ask for a go-ahead in chat
  before merging (user's stated preference), then run `gh pr merge`.
- **Python**: 3.12.6 available (`python`/`py`). A dedicated project venv
  (`.venv`) will be created in Phase 1 per the autopilot instruction to use a
  project-local env, not the global interpreter.
- **Commit signing**: SSH-based, configured locally (per-repo, not global) —
  see `CONTRIBUTING.md` "Signed commits" section for the reusable setup
  steps.

## Next recommended step

Merge the Step 0.4 PR, confirm its checks pass, add required status checks to
`main`'s branch protection to match, then start Phase 1 — Project
Scaffolding & Infrastructure (Step 1.1: project skeleton).
