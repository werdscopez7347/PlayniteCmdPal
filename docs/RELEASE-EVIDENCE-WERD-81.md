# WERD-81 release MSIX evidence record

**Status (2026-11-17): release tooling implemented and self-tested, continuous integration green on both
platforms. The Windows package build, signing and archive inspection have not been executed yet, so no
release-candidate MSIX exists and none of the WERD-81 acceptance criteria are complete.**

This record accompanies the release pipeline in [`scripts/release/`](../scripts/release/) and the process in
[Release packaging](RELEASE-PACKAGING.md#10-release-msix-build-and-inspection-werd-81). It exists so the package
evidence is recorded in one place, with explicit statements about what ran, what did not, and what the remaining
run must produce. Nothing here authorizes publication.

## 1. Why the packages are not built yet

The WERD-81 implementation session had no Windows host, .NET SDK, MSBuild, Windows SDK, `signtool.exe` or
`makeappx.exe`. `dotnet`, `pwsh`, `signtool` and the MSIX packaging toolchain were all unavailable, and the
sandbox has no access to the NuGet restore graph. A release MSIX cannot be produced, signed or installed from
that environment, so this branch does not fabricate package hashes or claim a build.

What the branch does provide is the deterministic pipeline that performs the run on the supported Windows build
machine, plus the tests that prove the inspection logic rejects the failure modes the acceptance criteria care
about.

## 2. What was executed in this session

| Step | Command | Result |
| --- | --- | --- |
| Repository preflight | `python -m unittest discover -s scripts/release/tests -v` (case `test_repository_matches_reviewed_expectations`) | 33 preflight checks pass: manifest, project, central properties, publish profiles, notices and the `10.0.26100.84` SDK pin agree with `scripts/release/release_expectations.json`. |
| Release-tool self-tests | `python -m unittest discover -s scripts/release/tests` | 35 tests pass (inspection pass/fail paths, preflight drift detection, signing/subject gating, dirty-tree gating, build orchestration with stub `dotnet`/`signtool`, evidence generation). |
| CI (PR #42) | GitHub Actions on the pull request | `Restore, build, and test (Windows)` pass (2m04s) and `Release tooling self-tests (cross-platform)` pass (7s on Ubuntu); `Analyze C#` and `CodeQL` pass. The Windows job runs `scripts/ci.ps1`, whose `Invoke-PythonStep` exits non-zero on failure (127 when `python` is absent), so the pass is proof that the 35 self-tests also pass on `windows-latest`. It is **not** a package build. |
| Build-command plan | `python scripts/release/release_tool.py build --dry-run` | Prints the two `dotnet publish` invocations and the `signtool sign`/`verify` steps without executing them. |
| MSIX generation | — | **Not executed.** No Windows host or .NET SDK. |
| Signing / `signtool verify` | — | **Not executed.** No certificate and no `signtool`. |
| Archive inspection of real packages | — | **Not executed.** No packages exist. |
| Install / launch / activation | — | Out of scope; tracked by WERD-82. |

Test-only fixtures are synthetic ZIP archives. They prove the checks work; they are not evidence about the
product's own package.

## 3. Acceptance criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| x64 package builds, signs, and passes package inspection | **Open** | Pipeline implemented; run outstanding. |
| ARM64 package builds, signs, and passes package inspection | **Open** | Pipeline implemented; run outstanding. |
| Package contents match the reviewed dependency inventory | **Open** | `inspect` enforces presence, package-source byte equality, forbidden-content and unreviewed-file gates; the inventory must be regenerated after the PR #41 version bumps before the run. |
| Required licenses/notices are present in each package | **Open** | `inspect` compares `LICENSE`, `THIRD-PARTY-NOTICES.md` and `Microsoft-PowerToys-LICENSE.txt` with the repository copies and the RID-specific runtime notice with its reviewed SHA-256. |
| Hashes and reproducible build evidence are recorded | **Open** | `build` writes `evidence.json`, `evidence.md`, `SHA256SUMS`, extracted `AppxManifest.xml` files, per-file payload hashes and every command with its exit code. |
| No package is submitted or published by this issue | Satisfied by design | The tooling has no upload, submission or publishing step and writes only to the git-ignored `artifacts/` tree. |

## 4. Completing the record on Windows

Run from a clean checkout of the merge commit on the supported Windows build machine:

```powershell
dotnet restore .\PlayniteCmdPal.sln
pwsh -File scripts/licensing/New-DependencyInventory.ps1 -Configuration Release
python scripts/release/release_tool.py preflight
$env:PLAYNITECMDPAL_MSIX_PFX_PASSWORD = '<pfx password>'
python scripts/release/release_tool.py build `
    --inventory artifacts/dependency-inventory.json `
    --certificate-pfx C:\secure\PlayniteCmdPal-test-signing.pfx
```

The run must exit `0`. Then copy the values below from `artifacts/release/0.0.8.0/evidence.md` and
`evidence.json`, attach the bundle to the WERD-81 review, and leave the packages out of Git.

| Field | Value |
| --- | --- |
| Source commit | _to be recorded by the run_ |
| Windows build / .NET SDK / MSBuild / signtool | _to be recorded by the run_ |
| x64 package filename, size, SHA-256 | _to be recorded by the run_ |
| ARM64 package filename, size, SHA-256 | _to be recorded by the run_ |
| Signing certificate subject and thumbprint | _subject must equal `CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70`; record the thumbprint without the private key_ |
| `signtool verify /pa /all` result | _to be recorded by the run_ |
| Inspection result (x64 / ARM64) | _to be recorded by the run_ |
| Regenerated inventory SHA-256 | _to be recorded by the run_ |

## 5. Why the earlier ARM64 artifact is not reused

PR #40 recorded `PlayniteCmdPal_0.0.8.0_arm64.msix` (42,589,226 bytes, SHA-256
`4DF5ABA49B151F291B4B85FF370FAB74240BBEFCB7F6A4FEB99CC11F444A8FF1`) from the WERD-77 branch. That artifact is
historical evidence only and must not be reused or carried into a release:

- It was produced with the `10.0.26100.87` targeting pack, not the `10.0.26100.84` package selected by the
  WERD-76 REDIST review that governs distribution (see the reconciliation note in
  [Release packaging](RELEASE-PACKAGING.md#release-pin-reconciliation-2026-11-17)).
- It predates the merged dependency bumps in PR #41 (`Microsoft.Windows.CsWinRT 2.3.1`,
  `Shmuelie.WinRTServer 2.2.1`, `Microsoft.CommandPalette.Extensions 0.12.260812002`,
  `Microsoft.Windows.SDK.BuildTools.MSIX 1.7.261102100`), so its payload no longer matches the current
  dependency graph.
- There is no matching x64 package from the same source revision, transaction or inspection run.

## 6. Signing model

Store-distributed packages are signed by Microsoft after certification; no publisher-managed production
certificate is required for that path (see [MSIX signing](MSIX-SIGNING.md)). A local release candidate still has
to be signed to prove the package identity is valid and installable: use a test certificate whose subject equals
the manifest Publisher (`CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70`), keep the PFX and its password outside the
repository, and let `release_tool.py` run `signtool sign` and `signtool verify /pa /all /v`. The tool records the
signer subject and fails when it differs from the Publisher. This validates signability and identity alignment; it
does not claim Store certification or a trusted production certificate.

## 7. Known risks and follow-ups for the Windows run

1. **MSBuild packaging flags are unvalidated on Windows in this branch.** The pipeline uses
   `dotnet publish` with `-p:GenerateAppxPackageOnBuild=true`, `-p:UapAppxPackageBuildMode=SideloadOnly`,
   `-p:AppxBundle=Never` and `-p:AppxPackageDir=...`, which is the documented single-project MSIX pattern. If the
   project's packaging targets require a different switch, the run fails loudly and records the failing command;
   fix the command (or pass `--msbuild-property`) and re-run rather than editing evidence by hand.
2. **Dependency inventory is stale.** The audit tables in [Licensing and release readiness](LICENSING-AND-RELEASE.md)
   record the 2026-11-01 graph. PR #41 moved four shipped package versions, so the inventory must be regenerated
   and the licensing tables updated before the WERD-81 run; `inspect --inventory` compares its shipped
   classifications and versions against the reviewed expectations.
3. **Runtime-notice hash.** The expected `.NET` runtime notice SHA-256
   (`6D15E10A101C6BFFF2AB4429ED061BF76C456FC4B23AD6B03E0D0F8377148A21`) is the WERD-77/78 value for .NET SDK
   10.0.403. A different .NET runtime patch changes the notice file; the run fails with the observed hash so the
   reviewer can confirm and update `release_expectations.json` deliberately.
4. **Payload review.** `build` runs inspection in strict mode, so any payload file that is not attributable to the
   app, the reviewed dependency assemblies or the .NET runtime fails the release gate. Classify intentional
   additions in `release_expectations.json`; never weaken the gate to make a run pass.
5. **Python prerequisite.** The tool needs Python 3.9+ on the build machine. It uses only the standard library;
   no package installation is required.
