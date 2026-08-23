# Contributing to PolicyPal

This document is the delivery contract for the project. It summarizes the Git
Workflow, Branching & Pull Request Strategy section of `files/plan.md` — read
that file for full detail and rationale. Every change, human or agent, ships
through this process. No exceptions.

## Branching model

`main` is the only long-lived branch. It is protected, always green, and
always deployable. Every change lands on a short-lived branch cut from `main`
and is squash-merged back through a reviewed pull request.

**Naming:** `<type>/<scope>-<short-kebab-summary>`, e.g.
`feat/rag-streaming-generation`, `fix/sse-stream-not-closing`,
`security/tenant-isolation-audit`.

| Type       | Prefix        | Used for                                    | Version bump |
| ---------- | ------------- | -------------------------------------------- | ------------ |
| Feature    | `feat/`       | New user-facing capability or module         | MINOR        |
| Bug fix    | `fix/`        | Correcting broken behavior                   | PATCH        |
| Hotfix     | `hotfix/`     | Urgent production defect, fast-tracked       | PATCH        |
| Refactor   | `refactor/`   | Internal restructuring, no behavior change   | none         |
| Performance| `perf/`       | Measurable latency/cost/memory improvement   | PATCH        |
| Tests      | `test/`       | Adding or improving tests only               | none         |
| Docs       | `docs/`       | README, plan, ADRs, API docs                 | none         |
| Chore      | `chore/`      | Dependency bumps, tooling, scaffolding       | none         |
| Build      | `build/`      | Dockerfiles, Compose, packaging              | none         |
| CI         | `ci/`         | GitHub Actions workflows and pipeline config | none         |
| Security   | `security/`   | Vulnerability remediation, auth hardening    | PATCH        |
| Revert     | `revert/`     | Reverting a previously merged PR             | PATCH        |

Rules:
- Lowercase, kebab-case, no personal names, no `temp`/`tmp`/`mybranch`.
- Include the issue ID when one exists: `fix/PP-231-duplicate-chunk-upsert`.
- One branch = one logical change.
- Maximum branch lifetime: 3 days. Rebase onto `main` daily.

## Commits — Conventional Commits

```
<type>(<scope>): <imperative summary under 72 chars>

<optional body: what changed and why, wrapped at 100 chars>

<optional footer: BREAKING CHANGE: …, Closes #123>
```

Allowed types: `feat`, `fix`, `hotfix`, `refactor`, `perf`, `test`, `docs`,
`chore`, `build`, `ci`, `security`, `revert`.

Allowed scopes: `repo`, `core`, `domain`, `ports`, `rag`, `router`,
`guardrails`, `auth`, `tenant`, `chunking`, `embedding`, `vectorstore`,
`cache`, `eventbus`, `persistence`, `api`, `admin`, `workers`, `frontend`,
`chat`, `eval`, `docker`, `ci`, `deps`.

- Use the imperative mood: "add", not "added" or "adds".
- Breaking changes: `!` after the type, or a `BREAKING CHANGE:` footer.
- No `wip`, `fix stuff`, `.`, `update`. Squash those away before opening a PR.
- Never commit secrets, `.env` files, credentials, generated documents, or
  `node_modules`.
- Commits on `main` must be signed (SSH or GPG). See below for setup.

`commitlint.config.js` enforces this automatically via the pre-commit
`commit-msg` hook.

## Pull requests

- PR title uses the exact same Conventional Commits format — it becomes the
  squash-merge commit message on `main`.
- Apply the type label (auto-applied by `.github/labeler.yml` from the branch
  prefix) and a `phase-N` label tying it back to `files/plan.md`.
- Use the template matching the branch type
  (`.github/PULL_REQUEST_TEMPLATE/*.md`).
- Include: what changed, why, how it was validated, linked issue, and a risk
  and rollback note for anything touching auth, tenancy, migrations, or the
  RAG pipeline.
- Target under 400 changed lines. Split larger work into stacked PRs.

## Merge policy

- **Squash and merge only.** One PR becomes exactly one commit on `main`.
- **Rebase, never merge commits**, when updating a branch from `main`.
- Branches are deleted automatically on merge.
- Force-push is allowed on your own feature branch only, never on `main`.

## Branch protection on `main`

- Direct pushes blocked — everything goes through a PR.
- Linear history required; force-push and deletion blocked for everyone
  (`enforce_admins` is on).
- Signed commits required.
- Conversations must be resolved before merging.
- Required status checks (added in Step 0.4) must pass before merge.

> **Solo-maintainer note:** `required_approving_review_count` is currently 0
> repo-wide, since GitHub does not allow self-approval and there is no second
> reviewer yet. `.github/CODEOWNERS` still documents where two approvals
> should apply once a collaborator joins — see the note in that file.

## Signed commits — one-time setup

Commits on `main` must be signed. SSH-based signing is the simplest option:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/<name>_signing -N "" -C "you@example.com signing"
gh ssh-key add ~/.ssh/<name>_signing.pub --type signing --title "<name> commit signing"
git config gpg.format ssh
git config user.signingkey ~/.ssh/<name>_signing.pub
git config commit.gpgsign true
```

(Use `git config --global` instead if you want this for every repo, not just
this one.)

## Local pre-commit hooks

Installed via `pre-commit` (`pip install pre-commit && pre-commit install
--hook-type pre-commit --hook-type commit-msg`):

- `ruff` lint + format on staged Python files (`backend/`).
- `mypy --strict` on `backend/src/`.
- `eslint` + `prettier` on staged frontend files.
- `commitlint` enforcing Conventional Commits on the commit message.
- `gitleaks` blocking secrets before they're ever committed.
- A guard blocking `.env`, `*.pem`, `*.key`, `data/gov_pdfs/*`,
  `data/synthetic/*` from being staged at all.

## The per-step delivery loop

Every implementation step in `files/plan.md` follows this loop:

```
1. git checkout main && git pull --rebase origin main
2. git checkout -b <type>/<scope>-<summary>
3. Implement the step. Add tests. Update README.md.
4. Run the local gates: ruff, mypy, pytest, eslint, tsc.
5. git add -p && git commit -S -m "<type>(<scope>): <summary>"
6. git push -u origin <branch>
7. Open a PR against main using the matching template.
   Apply the type label and the phase label. Link the issue.
8. CI runs. Fix anything red. Address review comments with follow-up commits.
9. Squash-merge into main. Delete the branch.
10. Tag a release when a phase completes.
```

No step is done until its branch is merged into `main` through a green,
reviewed PR.
