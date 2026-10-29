# Repository Governance and Release Policy

Status of GitHub-hosted repository settings for WERD-66. Last audited **2026-10-28** via the GitHub API.
Committed files (workflows, Dependabot config, CODEOWNERS, SECURITY.md) do not enforce these settings by themselves; the items below must be confirmed in the repository's **Settings** UI or via an admin-scoped API token.

Legend: **Verified** = confirmed true via API. **Blocked** = change attempted via API but denied (token lacks repository-administration permission); needs the maintainer to apply it in the GitHub UI. **Needs decision** = maintainer judgment required.

## Branch model (verified)

- Default and release branch: `main`. Integration branch: `dev`. Feature branches target `dev`; `dev` is merged to `main` via pull request.
- Both `main` and `dev` currently have **no branch protection and no rulesets** (API: `GET /rulesets` → `[]`, both branches `protected: false`).

## Default-branch ruleset (blocked — apply in UI)

Creating the ruleset via API returned `403 Resource not accessible by integration`. Apply manually:

**Settings → Rules → Rulesets → New ruleset → New branch ruleset**

1. Name: `Protect main`. Enforcement: **Active**.
2. Target branches: add **Include default branch**.
3. Enable **Restrict deletions** and **Block force pushes**.
4. Enable **Require a pull request before merging** with **Required approvals: 0**.
   - Rationale: this is a solo-maintained repository; GitHub does not count self-approval, so requiring ≥1 approval would make every merge impossible. The PR requirement itself still forces CI to pass and keeps history reviewable.
5. Enable **Require status checks to pass** and add exactly these checks (both have successful runs on `main` and on PRs, verified 2026-10-28):
   - `Restore, build, and test (Windows)` (Windows CI, `.github/workflows/ci.yml`)
   - `Analyze C#` (CodeQL, `.github/workflows/codeql.yml`)
   - Do not add the GitHub Advanced Security `CodeQL` check or `CodeRabbit`; they are app-reported and not guaranteed on every PR.
   - Leave "Require branches to be up to date" off initially to avoid merge-queue friction for a solo maintainer; revisit if stale merges cause breakage.

Optionally create a second, lighter ruleset for `dev` with only **Restrict deletions** and **Block force pushes** (needs decision).

## Security settings

| Setting | State (2026-10-28) | Action |
| --- | --- | --- |
| Private vulnerability reporting | **Disabled** (verified: API returned `enabled: false`; enabling via API was blocked with 403) | Enable at **Settings → Advanced Security → Private vulnerability reporting**. SECURITY.md already points reporters at this flow. |
| Dependabot alerts | Unverified (API read/write denied) | Confirm enabled at **Settings → Advanced Security → Dependabot → Dependabot alerts**. |
| Dependabot security updates | Unverified (API read/write denied) | Confirm enabled at the same page. Version updates are already configured in `.github/dependabot.yml` (verified: Dependabot update runs exist on `dev`). |
| CodeQL code scanning | **Working** (verified: successful scheduled and push-triggered `CodeQL` runs; GHAS check reports on PRs) | None. |
| Secret scanning / push protection | Unverified (API denied) | Confirm enabled at **Settings → Advanced Security** (free for public repositories). |

## Actions permissions (unverified — confirm in UI)

API read of Actions permissions was denied. Confirm at **Settings → Actions → General**:

- Workflow permissions: **Read repository contents and packages permissions** (read-only default).
- "Allow GitHub Actions to create and approve pull requests": **off**.

Defense-in-depth already committed: both workflows declare top-level `permissions: contents: read` (CodeQL's job adds only `security-events: write`), use `persist-credentials: false`, timeouts, and concurrency cancellation.

## Repository features

- Visibility: **public** (verified). Needs maintainer confirmation this is intentional — note the repository currently has **no LICENSE file** (verified: `licenseInfo: null`), so the code is publicly visible but not licensed for reuse. Choose and commit a license before any release.
- Discussions: **enabled** (verified). Needs decision — nothing in the repo links to Discussions; disable it at **Settings → General → Features** if it is not going to be used, to avoid an unwatched inbox.
- Wiki: disabled (verified, good). Issues and Projects: enabled (verified; issue templates are in use).
- "Automatically delete head branches" after merge: **off** (verified). Recommended **on** for tidiness (needs decision; apply at **Settings → General**).

## CI status badges

README badges for Windows CI and CodeQL were added only after verifying first successful runs on `main` (Windows CI run `40351115311`, CodeQL runs `40490182715` and `40351115315`).

## Release policy

- **No GitHub Releases or tags exist, and none should be created yet** (verified: `latestRelease: null`).
- Preconditions for the first release, all currently unmet:
  1. A license file is committed and licensing of all dependencies is reviewed.
  2. A tagged build artifact has passed CI **and** a documented manual smoke test (local deployment + Playnite integration acceptance criteria).
  3. A release checklist exists (artifact contents, versioning scheme, changelog, signing decision).
- Until then, the only "supported version" remains the default branch head, as stated in SECURITY.md.

## Re-audit checklist

After applying the UI changes above, re-verify with:

```bash
gh api repos/werdscopez7347/PlayniteCmdPal/rulesets
gh api repos/werdscopez7347/PlayniteCmdPal/private-vulnerability-reporting
gh api repos/werdscopez7347/PlayniteCmdPal/vulnerability-alerts -i   # 204 = alerts enabled
gh api repos/werdscopez7347/PlayniteCmdPal/actions/permissions/workflow
```
