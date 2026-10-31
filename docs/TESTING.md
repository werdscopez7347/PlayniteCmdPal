# Testing

This page explains what is tested, where each check runs, and how to run it. For installing the toolchain and deploying the extension, see [Developer Setup](DEVELOPER-SETUP.md).

**Status (2026-10-31):** Automated coverage is synthetic and is designed to run without Playnite, PowerToys, a personal game library, or secrets. The test commands below are the ones executed by `scripts/ci.ps1`, which Windows CI and CodeQL run on `windows-latest`. The latest verified Windows CI run passed restore, Release build, both test projects, and the .NET Framework smoke test ([run 41177945707](https://github.com/werdscopez7347/PlayniteCmdPal/actions/runs/41177945707)); see the verification evidence section of [Developer Setup](DEVELOPER-SETUP.md) for the evidence trail and its limits.

## Test projects

| Project | Target | References | Needs Playnite installed? |
|---|---|---|---|
| `PlayniteCmdPal.Core.Tests` | `net10.0` | `PlayniteCmdPal.Core` | No |
| `PlayniteCmdPal.Playnite.Tests` | `net10.0` | `PlayniteCmdPal.Playnite`, `PlayniteCmdPal.Snapshot` | No |

Neither test project references `PlayniteCmdPal/` (the CmdPal host) or `PlayniteCmdPal.PlaynitePlugin/` (the `net462` companion plugin). The companion plugin is only compiled; its SDK usage is exercised indirectly by the behavior it delegates to the shared snapshot assembly.

Test data is generated in the test process and written to a temporary directory (`%TEMP%\PlayniteCmdPal.Tests\<guid>`). Each test class that touches disk owns and deletes its directory. No test reads `%LOCALAPPDATA%`, Playnite storage, `playnite.log`, or any real library export.

## Coverage map

### Domain and search (`PlayniteCmdPal.Core.Tests`)

| File | Covers |
|---|---|
| `GameEntryTests` | Required-field validation and parameter names, optional fields defaulting to unknown, record value equality/hashing, `with` expressions preserving identity, display text not being normalized by the model. |
| `GameSearchTests` | Baseline ranking order (exact, prefix, word-prefix, substring), case-insensitivity, duplicate titles, tie-breaks, blank/null query, empty catalog, invalid entries. |
| `GameSearchRankingTests` | Query trimming versus untrimmed stored titles, multi-word and partial queries, word-boundary rules (only non-alphanumeric characters start a word), earliest-match index ordering, ordinal ID ordering for duplicate titles, canonical duplicate-ID selection independent of input order, returned collection immutability, single enumeration of the catalog, argument precedence (blank query short-circuits), and a 5,000-entry determinism check. |

### Snapshot contract (`PlayniteCmdPal.Playnite.Tests`)

| File | Covers |
|---|---|
| `CatalogSnapshotContractTests` | Non-UTC timestamps rejected, UTC converted from another offset accepted, defensive copy of the game list, read-only collections, duplicate/null records, `MaxGames` boundary, canonical-GUID identity rules (trimming must not change identity), name and optional-field normalization, install-state preservation, and the pinned schema constants. |
| `CatalogSnapshotParserTests` (pre-existing) | Envelope validation, timestamp formats, allowlisted fields, unsupported schema, over-limit records, JSON depth, serializer round trip. |
| `CatalogSnapshotParserProtocolTests` | Property order independence, empty input, trailing content, near-miss property names not being allowlisted, Unicode escapes, `null` versus absent optional fields, wrong optional-field types, missing required fields skipping only that record, non-object array items, first-valid-record-wins for duplicate IDs, model-validation failures counted as skipped, any non-1 schema reported as `UnsupportedSchema`, non-numeric schema reported as `Malformed`, calendar/timezone-invalid timestamps, the exact 32 MiB and 100,000-record limits, and parsed results surviving mutation of the input buffer. |
| `CatalogSnapshotSerializerTests` (pre-existing) | Escaping and round trip, isolated surrogate replacement, empty library, cancellation, write-failure visibility, and the `System.Text.Json`-free reference check for the shared assembly. |
| `CatalogSnapshotSerializerContractTests` | Argument validation before writing, envelope field set and order, UTC wire format, no BOM, per-record field set, deterministic output, destination left open, non-writable destination failure. |

### Publication and refresh

| File | Covers |
|---|---|
| `SnapshotFilePublisherTests` (pre-existing) | Atomic create/replace, canceled publication preserving the previous file, concurrent publications, oversized publication cleanup. |
| `SnapshotFilePublisherContractTests` | Validation before filesystem contact, pre-canceled publication creating nothing, repeated replacement, overwriting a corrupt file, concurrent first-creation races, omitted optional fields, and temporary files never remaining after a failed replacement. |
| `CatalogExportCoordinatorTests` (pre-existing) | Burst coalescing, follow-up scheduling, failure isolation, dispose semantics. |
| `CatalogExportCoordinatorLifecycleTests` | Constructor validation, zero debounce, requests made before the loop starts, a burst inside the debounce window collapsing to one export, requests during an export scheduling exactly one follow-up, exports never overlapping, error reporting without escaping the loop, faulted-task handling, disposal canceling the delegate's token, single-run enforcement, idempotent disposal, and disposing before or while running. |
| `PlayniteCatalogAdapterTests` (pre-existing) | Missing file, mapping to `GameEntry`, empty library, staleness boundary, last-known-good retention, reconnect, cache interval, coalescing, skipped records. |
| `PlayniteCatalogAdapterPolicyTests` | Default path and policy constants, the adapter never creating or deleting the snapshot, reading while a writer holds the file open, a directory at the snapshot path being reported as unavailable rather than missing, invalid records keeping the library usable, empty/unsupported files, adapter output ranking through `GameSearch`, interval boundary behavior, repeated failures retaining the same last-known-good data, concurrent callers sharing a read, pre-canceled callers, immutability of returned results, and a 2,000-game round trip through the real publisher and adapter. |

## What runs where

| Check | Local | Windows CI | CodeQL workflow | Requires Windows | Requires Playnite / PowerToys |
|---|---|---|---|---|---|
| `dotnet restore` / `dotnet build` (Release) | Yes, via `scripts/ci.ps1` | Yes | Yes | Yes (MSIX/WinUI targets) | No |
| `PlayniteCmdPal.Core.Tests` | Yes | Yes | Yes | No (runs on any OS with the .NET 10 SDK, but the repository's shared script is Windows-only) | No |
| `PlayniteCmdPal.Playnite.Tests` | Yes | Yes | Yes | No for the unit/contract tests; the shared script itself is Windows-only | No |
| .NET Framework snapshot smoke test (`scripts/test-playnite-snapshot-netfx.ps1`) | Yes | Yes | Yes | Yes (Windows PowerShell 5.1 / .NET Framework CLR) | No |
| CodeQL C# analysis | No | n/a | Yes | Yes (workflow runs on `windows-latest`) | No |
| MSIX deploy + Command Palette extension reload | Manual | No | No | Yes | PowerToys |
| Companion plugin packaging (`scripts/package-playnite-plugin.ps1`) | Manual | No | No | Yes | No (publishes and smoke-tests the `.pext`) |
| Real-library verification (`tools/CatalogVerifier` and the [Catalog Bridge checklist](CATALOG-BRIDGE.md#manual-playnite-verification-still-required)) | Manual | No | No | Yes | Playnite (PowerToys only for the launch UI) |
| Launch-by-ID URI smoke test | Manual | No | No | Yes | Playnite + PowerToys, plus one real game |

Run status honesty: the suites described here were written and reviewed in a Linux environment that has no .NET SDK, PowerShell, or access to Microsoft's SDK/CDN hosts or NuGet, so they could not be executed there. Syntax and convention checks were run instead, and none of that counts as a passing test run. The authoritative result is the Windows CI run (and the .NET Framework smoke step) attached to the pull request that adds or changes them. Do not mark a test as passing locally unless you actually ran it.

The real-library and launch smoke tests are intentionally outside the automated suites: they depend on a particular installed Playnite, a particular PowerToys version, and one user's library. Normal CI must never require them.

`scripts/ci.ps1` is the single source of truth for the automated checks. Windows CI and the CodeQL workflow invoke it instead of repeating commands, so a step cannot drift between a developer machine and CI. When you add a check, add it to that script rather than only to the workflow.

## Running the tests

### Everything CI runs

From the repository root in PowerShell on Windows:

```powershell
.\scripts\ci.ps1
```

It prints the exact `dotnet` command it runs before each step, stops at the first failure, reports the step name and exit code, and returns that exit code.

### One test project while iterating

```powershell
dotnet test .\PlayniteCmdPal.Core.Tests\PlayniteCmdPal.Core.Tests.csproj
dotnet test .\PlayniteCmdPal.Playnite.Tests\PlayniteCmdPal.Playnite.Tests.csproj
```

Drop `--configuration Release --no-build --no-restore` (used by the script) when you have not built first, or add `--no-restore` after an initial restore for a faster loop.

### A single class or test name

```powershell
dotnet test .\PlayniteCmdPal.Playnite.Tests\PlayniteCmdPal.Playnite.Tests.csproj --filter "FullyQualifiedName~PlayniteCatalogAdapterPolicyTests"
dotnet test .\PlayniteCmdPal.Core.Tests\PlayniteCmdPal.Core.Tests.csproj --filter "FullyQualifiedName~GameSearchRankingTests"
```

### Verbose output for a failing case

```powershell
dotnet test .\PlayniteCmdPal.Core.Tests\PlayniteCmdPal.Core.Tests.csproj --logger "console;verbosity=detailed" --filter "FullyQualifiedName~QueryIsTrimmedBeforeMatching"
```

### Coverage at a glance

The suites hold 251 test cases (facts plus `[InlineData]` rows) split across the two projects: 69 for domain/search and 182 for the snapshot contract, publication, refresh, and adapter policy. The coverage added for [WERD-62](https://linear.app/werdscopez7347/issue/WERD-62/expand-automated-tests-and-finalize-the-developer-setup-guide) accounts for 148 of them. Counts drift as tests change; the per-file table above is the authoritative map.

### Expected outcome

A passing run ends with `Passed! - Failed: 0, Passed: <n>, Skipped: 0, Total: <n>` for each project. Treat a skipped test as a gap: the suites are designed to have no conditional skips and no environment-gated tests, so a skip means the test was disabled and needs review.

## Test conventions

- **Synthetic data only.** Use obvious fictional titles and deterministic GUIDs built in-process. Never copy IDs, titles, source names, or paths from a real library, log, or snapshot.
- **No environment dependence.** Do not read `%LOCALAPPDATA%`, `%APPDATA%`, the registry, the clock, or the network. Pass an explicit path and use a fake `TimeProvider` when time matters.
- **Own your temporary files.** Create `%TEMP%\PlayniteCmdPal.Tests\<guid>` in the constructor and delete it in `Dispose`, ignoring `IOException` during cleanup.
- **Deterministic concurrency tests.** Prefer synchronization primitives (`TaskCompletionSource`, `SemaphoreSlim`) over fixed sleeps. When a test must prove *coalescing*, hold the in-flight export open until every extra request has been issued; a short sleep can let the export finish and split the burst into two exports. `TaskCompletionSource` is not `IDisposable`, so do not declare it with `using`.
- **Assert one contract per test, with the reason.** When a test pins a rule that a future refactor might be tempted to "fix" (for example, only non-alphanumeric characters start a word match), say so in a comment.
- **Do not assert behavior the code does not promise.** If a case depends on an unverified framework policy (for example, how a particular JSON reader treats a lone surrogate escape), do not encode it as a test. Move it to the "Known gaps" list instead.
- **Keep the suites fast.** Everything runs in seconds; total CI time is dominated by restore and build, not by tests. Avoid tests that would need multi-second timeouts.

## Platform-sensitive assertions

Two assertions depend on operating-system behavior rather than on project code, so treat a failure there as "check Windows semantics first" rather than "the adapter regressed":

- `PlayniteCatalogAdapterPolicyTests.DirectoryPathInsteadOfFileIsReportedAsUnavailableRatherThanMissing` opens a **directory** as if it were the snapshot file. Windows reports that as `UnauthorizedAccessException` and Linux as an I/O error; the adapter maps both to `Unavailable`. Neither code path could be executed while this suite was written, so if the mapping differs on Windows this test is the one to inspect first.
- `SnapshotFilePublisherContractTests.TemporaryFilesNeverRemainAfterAFailedPublication` occupies the destination with a directory so `File.Replace`/`File.Move` fail deterministically. Directory placement is not covered by any recorded Windows run either.

Everything else asserts project-defined behavior (validation, ranking, parsing, publication, caching) and should behave identically on any OS with .NET 10.

## Known gaps

These are deliberately not automated yet; each needs a Windows host and, in most cases, installed applications.

- Clean-machine setup: the [Developer Setup](DEVELOPER-SETUP.md) steps have not been replayed on a freshly imaged Windows machine by an independent contributor.
- The companion plugin's Playnite event wiring (`OnDatabaseOpened`, game/source/platform collection changes, relevance filtering of game updates) is compiled but not unit tested, because `PlayniteApi` is supplied by the Playnite host. Its observable behavior is covered manually through the [Catalog Bridge checklist](CATALOG-BRIDGE.md#manual-playnite-verification-still-required).
- The CmdPal presentation layer (search page, ranking display, launch action) has no automated tests; it is exercised by manual deploy/reload and the launch-by-ID smoke test.
- No test verifies the real Playnite library contents against the snapshot (by design: that would require personal data).
- Minimum supported versions of Windows, Visual Studio, PowerToys, and Playnite are recorded as "validated once", not as tested minimums. See the contributor environment table in [Developer Setup](DEVELOPER-SETUP.md).
