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

### The first Windows attempt (2026-11-17)

The first run of the sequence in section 4 happened on the supported Windows build machine and stopped at the
first step, so it produced no package. Recorded because it is real evidence about the tooling:

| Step | Command | Observed result |
| --- | --- | --- |
| Restore | `dotnet restore .\PlayniteCmdPal.sln` | `Restore complete (5.0s)`, `Build succeeded in 5.5s`. |
| Inventory | `pwsh -File scripts/licensing/New-DependencyInventory.ps1 -Configuration Release` | **Failed:** `pwsh` is not installed on that machine (`CommandNotFoundException`). No inventory was written, so the `--inventory` gate could not pass. The documented command is now `powershell -File ...` (Windows PowerShell 5.1), which is the host the generator was validated on. |
| Preflight | `python scripts/release/release_tool.py preflight` | **PASS (33 checks)** against the real checkout: identity, `0.0.8.0`, `10.0.26100.84` pin, both publish profiles, notice copies, runtime-notice hashes and expectation coverage all agree. |
| Build | `python scripts/release/release_tool.py build --inventory artifacts/dependency-inventory.json --certificate-pfx C:\secure\PlayniteCmdPal-test-signing.pfx` | **Refused:** the working tree had uncommitted changes, so no publish ran and no evidence bundle was written. The revision in use did not say which paths were dirty; `build` now prints them (at most ten, then a count) and records them in `environment.source.dirtyPaths`. |
| Working tree | `git status` | The only entries were untracked `PlayniteCmdPal-Test.cer`, `PlayniteCmdPal-Test.pfx` and the MSBuild `PlayniteCmdPal/AppPackages/` output — no source edits. Staging the PFX by accident was therefore one `git add -A` away. `.gitignore` now covers `*.pfx`, `*.p12`, `*.cer`, `*.pvk` and `[Aa]ppPackages/`, and `build` warns (and records `environment.signing.certificateInsideRepository`) when the certificate path is inside the checkout. |

Nothing above is a substitute for the package run: the two MSIX files, the signatures and the inspection results
are still missing.

### The second Windows attempt (2026-11-19)

The checkout was cleaned (test certificate moved to `C:\secure\`, stale `AppPackages/` removed) and the sequence
was re-run. Packaging works; signing did not run:

| Step | Command | Observed result |
| --- | --- | --- |
| Working tree | `git status --short` | Empty after the certificate and packaging output were removed from the checkout. |
| Restore | `dotnet restore .\PlayniteCmdPal.sln` | `Restore complete (4.9s)`, `Build succeeded in 5.4s`. |
| Inventory | `powershell -File scripts\licensing\New-DependencyInventory.ps1 -Configuration Release` | **Ran under Windows PowerShell 5.1** and wrote `artifacts/dependency-inventory.json`: 4 shipped-runtime, 4 shipped-build, 12 test-only, 0 developer-tool, 0 unclassified, 5 review flags (4 in shipped classifications). The JSON SHA-256 has not been captured yet. |
| Preflight | `python scripts/release/release_tool.py preflight` | **PASS (33 checks)**. |
| Build (win-x64) | `python scripts/release/release_tool.py build --inventory artifacts/dependency-inventory.json --certificate-pfx C:\secure\PlayniteCmdPal-Test.pfx` | `dotnet publish` produced `artifacts\release\0.0.8.0\appx\win-x64\PlayniteCmdPal_0.0.8.0_x64_Test\PlayniteCmdPal_0.0.8.0_x64.msix`. Signing then failed with `Executable not found: signtool.exe` and the run stopped, so no signature, no inspection and no evidence bundle exist for either architecture. |

What this establishes: the single-project MSIX packaging switches used by `build`
(`GenerateAppxPackageOnBuild`, `UapAppxPackageBuildMode=SideloadOnly`, `AppxBundle=Never`) do produce one
architecture-specific package under the requested `AppxPackageDir`, and the package name and layout match the
expectations file. What it does not establish: any signature, any inspection result, the ARM64 package, or any
hash.

The `signtool.exe` failure is an environment issue, not a package issue: the Windows SDK installer does not add
its `bin` directory to `PATH`. `build` now resolves `signtool.exe` and `makeappx.exe` from
`%ProgramFiles(x86)%\Windows Kits\10\bin\<version>\x64` (newest SDK first) before falling back to the name, and
prints a warning naming `--signtool` when nothing is found.

The retry with the discovery fix found `C:\Program Files (x86)\Windows Kits\10\bin\10.0.26100.0\x64\signtool.exe`
and published the `win-x64` package again, then failed with `SignTool Error: The specified PFX password is not
correct`: the test PFX is password-protected and the password is no longer known. `build` now names both remedies
(set the password variable, or sign with `--certificate-thumbprint` from `Cert:\CurrentUser\My`) instead of
reporting only that signing failed; the recovery paths are in [MSIX signing](MSIX-SIGNING.md#6-signing-a-package-when-the-pfx-password-is-unknown).

The fix is exercised on `windows-latest` by the CI job: it runs the full self-test suite (45 tests, including the
SDK tool-discovery cases) through `scripts/ci.ps1` in 2m02s, so the resolution path is known to work on Windows
before the next manual run.

### The third and fourth Windows attempts (2026-11-19)

| Step | Result |
| --- | --- |
| Signing certificate | A test certificate with the manifest Publisher as subject was created in `Cert:\CurrentUser\My` (thumbprint `018EBC36ABEB48F1550AFD658369B2C9BC9FB560`) and its public `.cer` imported into `Cert:\CurrentUser\Root`. |
| Build | **Both packages built and signed**: `PlayniteCmdPal_0.0.8.0_x64.msix` (SHA-256 `99801D4C2AA21D3AE51F19B8C649296485D99A646E120A4B3E36EB909DA80B73`) and `PlayniteCmdPal_0.0.8.0_arm64.msix` (SHA-256 `CA159A805AC29220B2140F46F5C6F7563FD30FE6E39536F19FEE53AE02993FA7`); `signtool verify /pa /all /v` succeeded for both. |
| Identity check | Reported FAIL although the certificate was correct: signtool prints `Issued to: B5EE8A57-…` (the common name only) while the manifest Publisher is `CN=B5EE8A57-…`, and the comparison treated the missing prefix as a different subject. Fixed by comparing common names; a genuinely different certificate still fails. |
| Acceptance | Criteria 4, 5 and 6 passed; 1 and 2 failed only because of that identity comparison; criterion 3 failed and could not be diagnosed, because its detail text was static. The detail now names the failing check ids and messages, and `build` prints every failing check under each package verdict. |

Those hashes are from a run whose evidence bundle is not authoritative (the package verdicts were wrong), and re-signing
changes the bytes through the timestamp, so the recorded values will come from the next clean run.

Inventory review flags from that run, for the licensing gate: `Microsoft.NETFramework.ReferenceAssemblies` and
`.net462` (license URL only), `Microsoft.Windows.CsWinRT` 2.3.1 (license file in package), `Microsoft.Windows.SDK
.BuildTools.MSIX` 1.7.261102100 (`sdk_license.txt`), and `xunit.abstractions` (test-only, license URL only).

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

Run from a clean checkout of the merge commit on the supported Windows build machine. `git status --short` must
print nothing: `build` refuses an uncommitted revision, because evidence that cannot be tied to a commit is not
reproducible.

```powershell
dotnet restore .\PlayniteCmdPal.sln
powershell -File scripts\licensing\New-DependencyInventory.ps1 -Configuration Release
python scripts/release/release_tool.py preflight
$env:PLAYNITECMDPAL_MSIX_PFX_PASSWORD = '<pfx password>'
python scripts/release/release_tool.py build `
    --inventory artifacts/dependency-inventory.json `
    --certificate-pfx C:\secure\PlayniteCmdPal-test-signing.pfx
```

`build` validates the inventory and certificate paths before it starts publishing, so a missing file fails in
seconds rather than after two MSIX builds.

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
