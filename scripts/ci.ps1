[CmdletBinding()]
param ()

Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$solutionPath = Join-Path $repoRoot 'PlayniteCmdPal.sln'
$testProjectPath = Join-Path $repoRoot 'PlayniteCmdPal.Core.Tests\PlayniteCmdPal.Core.Tests.csproj'
$adapterTestProjectPath = Join-Path $repoRoot 'PlayniteCmdPal.Playnite.Tests\PlayniteCmdPal.Playnite.Tests.csproj'

if (-not (Test-Path -LiteralPath $solutionPath) -or -not (Test-Path -LiteralPath $testProjectPath) -or -not (Test-Path -LiteralPath $adapterTestProjectPath)) {
    [Console]::Error.WriteLine('ERROR: Expected solution or test project was not found relative to scripts/ci.ps1.')
    exit 1
}

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine('ERROR: .NET SDK 10 is required, but dotnet was not found on PATH.')
    exit 127
}

function Write-GitHubAnnotation {
    param (
        [Parameter(Mandatory)] [string] $Message,
        [string] $Title = ''
    )

    # GitHub check annotations are public, so only file/line and test names are reported.
    # Test output can contain local paths, so it is never copied into an annotation.
    # Workflow commands must reach the standard output stream verbatim; some runners do not
    # parse them from Write-Host, so use the console directly.
    if (-not $env:GITHUB_ACTIONS) {
        return
    }

    $escaped = $Message.Replace('%', '%25').Replace("`r", '%0D').Replace("`n", '%0A').Replace('\'', '%27')
    [Console]::Out.WriteLine("::error title=$Title::$escaped")
}

function Get-FailedTests {
    param ([Parameter(Mandatory)] [string] $TrxPath)

    if (-not (Test-Path -LiteralPath $TrxPath)) {
        return @()
    }

    try {
        [xml] $trx = Get-Content -LiteralPath $TrxPath -Raw
        return @($trx.TestRun.Results.UnitTestResult |
            ForEach-Object { if ($_.outcome -eq 'Failed') { '{0}' -f $_.testName } })
    }
    catch {
        return @()
    }
}

function Invoke-DotNetStep {
    param (
        [Parameter(Mandatory)]
        [string] $Name,

        [Parameter(Mandatory)]
        [string[]] $Arguments,

        # When set, test results are written to this directory so failures can be annotated.
        [string] $ResultsDirectory = ''
    )

    Write-Host ''
    Write-Host "==> $Name"

    $effective = $Arguments
    if ($ResultsDirectory) {
        if (Test-Path -LiteralPath $ResultsDirectory) {
            Remove-Item -LiteralPath $ResultsDirectory -Recurse -Force
        }

        New-Item -ItemType Directory -Path $ResultsDirectory -Force | Out-Null
        $effective = $Arguments + @('--logger', 'trx;LogFilePrefix=results', '--results-directory', $ResultsDirectory)
    }

    Write-Host ('dotnet ' + ($effective -join ' '))

    & dotnet @effective
    $exitCode = $LASTEXITCODE

    if ($ResultsDirectory) {
        $trx = Get-ChildItem -LiteralPath $ResultsDirectory -Filter '*.trx' -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($trx) {
            try {
                [xml] $trxDocument = Get-Content -LiteralPath $trx.FullName -Raw
                $counters = $trxDocument.TestRun.ResultSummary.Counters
                Write-Host ("Result: total={0} passed={1} failed={2} skipped={3}" -f $counters.total, $counters.passed, $counters.failed, $counters.notExecuted)
                if ($env:GITHUB_STEP_SUMMARY) {
                    Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value ("- {0}: total={1} passed={2} failed={3} skipped={4}" -f $Name, $counters.total, $counters.passed, $counters.failed, $counters.notExecuted)
                }
            }
            catch {
                Write-Host 'Result: test summary could not be read from the TRX file.'
            }
        }
    }

    if ($exitCode -ne 0) {
        [Console]::Error.WriteLine("ERROR: $Name failed with exit code $exitCode.")

        if ($env:GITHUB_STEP_SUMMARY) {
            Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value ("- FAILED: {0} (exit code {1})" -f $Name, $exitCode)
        }

        if ($ResultsDirectory) {
            $trx = Get-ChildItem -LiteralPath $ResultsDirectory -Filter '*.trx' -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            $failedTests = if ($trx) { Get-FailedTests -TrxPath $trx.FullName } else { @() }
            if ($failedTests.Count -gt 0) {
                foreach ($failedTest in $failedTests) {
                    [Console]::Error.WriteLine("FAILED: $failedTest")
                    Write-GitHubAnnotation -Title $Name -Message "Failed test: $failedTest"
                }
            }
            else {
                Write-GitHubAnnotation -Title $Name -Message "$Name failed with exit code $exitCode; no failing test was recorded in the TRX results."
            }
        }

        exit $exitCode
    }
}

Invoke-DotNetStep -Name '.NET SDK information' -Arguments @('--info')
Invoke-DotNetStep -Name 'Restore' -Arguments @('restore', $solutionPath)
Invoke-DotNetStep -Name 'Build (Release)' -Arguments @('build', $solutionPath, '--configuration', 'Release', '--no-restore')
Invoke-DotNetStep -Name 'Test core search (Release)' -Arguments @('test', $testProjectPath, '--configuration', 'Release', '--no-build', '--no-restore') -ResultsDirectory (Join-Path $repoRoot 'artifacts\test-results\core')
Invoke-DotNetStep -Name 'Test Playnite adapter (Release)' -Arguments @('test', $adapterTestProjectPath, '--configuration', 'Release', '--no-build', '--no-restore') -ResultsDirectory (Join-Path $repoRoot 'artifacts\test-results\adapter')

$frameworkPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$frameworkSmoke = Join-Path $repoRoot 'scripts\test-playnite-snapshot-netfx.ps1'
$pluginBuildDir = Join-Path $repoRoot 'PlayniteCmdPal.PlaynitePlugin\bin\Release\net462'
if (-not (Test-Path -LiteralPath $frameworkPowerShell)) {
    [Console]::Error.WriteLine('ERROR: Windows PowerShell 5.1 is required for the .NET Framework bridge smoke test.')
    exit 127
}

Write-Host ''
Write-Host '==> Test Playnite snapshot publication on .NET Framework (synthetic data)'
& $frameworkPowerShell -NoProfile -ExecutionPolicy Bypass -File $frameworkSmoke -SnapshotAssembly (Join-Path $pluginBuildDir 'PlayniteCmdPal.Snapshot.dll') -PluginAssembly (Join-Path $pluginBuildDir 'PlayniteCmdPal.PlaynitePlugin.dll')
if ($LASTEXITCODE -ne 0) {
    [Console]::Error.WriteLine("ERROR: .NET Framework snapshot smoke test failed with exit code $LASTEXITCODE.")
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host 'All local CI checks passed.'
