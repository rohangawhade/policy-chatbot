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

Finish Step 0.3 (open PR, merge on go-ahead), then Step 0.4 — CI pipelines
(`ci.yml`, `pr-lint.yml`, `secret-scan.yml`, `dependency-audit.yml`,
`docker-build.yml`, `migration-check.yml`, `release.yml`), which completes
Phase 0.
