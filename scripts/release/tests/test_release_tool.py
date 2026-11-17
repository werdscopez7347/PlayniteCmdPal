"""Self-tests for the PlayniteCmdPal release tool (scripts/release/release_tool.py).

Run from the repository root:

    python -m unittest discover -s scripts/release/tests -v

The suite is standard-library only. Inspection and preflight tests run on any
platform. Build-orchestration tests use stub dotnet/signtool executables and are
skipped on Windows because the stubs are POSIX shell scripts.
"""

import copy
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
RELEASE_DIR = TESTS_DIR.parent
REPO_ROOT = RELEASE_DIR.parents[1]

sys.path.insert(0, str(RELEASE_DIR))
sys.path.insert(0, str(TESTS_DIR))

import msix_fixture  # noqa: E402
import release_tool  # noqa: E402

EXPECTATIONS = release_tool.load_expectations(release_tool.DEFAULT_EXPECTATIONS)

REPO_SOURCE_FILES = (
    'LICENSE',
    'Directory.Build.props',
    'Directory.Packages.props',
    'PlayniteCmdPal.sln',
    'PlayniteCmdPal/PlayniteCmdPal.csproj',
    'PlayniteCmdPal/Package.appxmanifest',
    'PlayniteCmdPal/Properties/PublishProfiles/win-x64.pubxml',
    'PlayniteCmdPal/Properties/PublishProfiles/win-arm64.pubxml',
    'third-party/THIRD-PARTY-NOTICES.md',
    'third-party/Microsoft-PowerToys-LICENSE.txt',
)


def fixture_expectations(notice_bytes=None):
    expectations = copy.deepcopy(EXPECTATIONS)
    digest = release_tool.sha256_bytes(notice_bytes or msix_fixture.default_notice_bytes())
    for rid in expectations['runtimeNotice']['sha256ByRid']:
        expectations['runtimeNotice']['sha256ByRid'][rid] = digest
    # Synthetic packages are far smaller than a real self-contained MSIX.
    expectations['package']['minimumPackageBytes'] = 1
    return expectations


def write_fixture_expectations(path, notice_bytes=None):
    path = Path(path)
    path.write_text(json.dumps(fixture_expectations(notice_bytes), indent=2), encoding='utf-8')
    return path


def copy_repository_sources(destination):
    destination = Path(destination)
    for relative in REPO_SOURCE_FILES:
        source = REPO_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return destination


def failing_ids(report_or_checks):
    checks = report_or_checks['checks'] if isinstance(report_or_checks, dict) else report_or_checks
    return sorted({item['id'] for item in checks if item['status'] == release_tool.FAIL})


class PreflightTests(unittest.TestCase):
    def test_repository_matches_reviewed_expectations(self):
        checks = release_tool.preflight(str(REPO_ROOT), EXPECTATIONS)
        self.assertEqual([], failing_ids(checks),
                         msg='\n'.join(release_tool.format_checks(checks)))

    def test_manifest_version_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = copy_repository_sources(temp)
            manifest_path = repo / 'PlayniteCmdPal/Package.appxmanifest'
            manifest_path.write_text(
                manifest_path.read_text(encoding='utf-8-sig').replace(
                    'Version="{0}"'.format(EXPECTATIONS['package']['version']),
                    'Version="9.9.9.9"'),
                encoding='utf-8')
            checks = release_tool.preflight(str(repo), EXPECTATIONS)
            self.assertIn('preflight.manifest.version', failing_ids(checks))

    def test_sdk_pin_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = copy_repository_sources(temp)
            props_path = repo / 'Directory.Build.props'
            props_path.write_text(
                props_path.read_text(encoding='utf-8-sig').replace(
                    EXPECTATIONS['package']['windowsSdkPackageVersion'], '10.0.26100.87'),
                encoding='utf-8')
            checks = release_tool.preflight(str(repo), EXPECTATIONS)
            self.assertIn('preflight.props.windows-sdk-package', failing_ids(checks))

    def test_com_server_substitution_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = copy_repository_sources(temp)
            manifest_path = repo / 'PlayniteCmdPal/Package.appxmanifest'
            manifest_path.write_text(
                manifest_path.read_text(encoding='utf-8-sig').replace(
                    '<com:ExeServer', '<com:SurrogateServer').replace(
                    '</com:ExeServer>', '</com:SurrogateServer>'),
                encoding='utf-8')
            checks = release_tool.preflight(str(repo), EXPECTATIONS)
            self.assertIn('preflight.manifest.com-server', failing_ids(checks))

    def test_missing_notice_publish_copy_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = copy_repository_sources(temp)
            project_path = repo / 'PlayniteCmdPal/PlayniteCmdPal.csproj'
            project_path.write_text(
                project_path.read_text(encoding='utf-8-sig').replace(
                    'CopyToPublishDirectory="PreserveNewest"', 'CopyToPublishDirectory="Never"'),
                encoding='utf-8')
            checks = release_tool.preflight(str(repo), EXPECTATIONS)
            failures = failing_ids(checks)
            self.assertTrue(any(item.startswith('preflight.notice.') for item in failures), failures)


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.expectations = fixture_expectations()
        self.expectations_path = write_fixture_expectations(self.root / 'expectations.json')
        self.nuget = self.root / 'nuget'
        files = msix_fixture.package_files(str(REPO_ROOT))
        msix_fixture.write_nuget_package(
            self.nuget, 'Microsoft.Windows.SDK.NET.Ref', '10.0.26100.84',
            'Microsoft.Windows.SDK.NET.dll', files['Microsoft.Windows.SDK.NET.dll'])
        msix_fixture.write_nuget_package(
            self.nuget, 'Microsoft.Windows.CsWinRT', '2.3.1',
            'WinRT.Runtime.dll', files['WinRT.Runtime.dll'])
        msix_fixture.write_nuget_package(
            self.nuget, 'Shmuelie.WinRTServer', '2.2.1',
            'Shmuelie.WinRTServer.dll', files['Shmuelie.WinRTServer.dll'])
        msix_fixture.write_nuget_package(
            self.nuget, 'Microsoft.CommandPalette.Extensions', '0.12.260812002',
            'Microsoft.CommandPalette.Extensions.winmd',
            files['Microsoft.CommandPalette.Extensions.winmd'])

    def tearDown(self):
        self.temp.cleanup()

    def write_package(self, rid='win-x64', architecture='x64', **kwargs):
        files = msix_fixture.package_files(str(REPO_ROOT), rid=rid, architecture=architecture,
                                           **{key: kwargs.pop(key) for key in
                                              ('manifest_overrides', 'payload_overrides', 'drop')
                                              if key in kwargs})
        write_kwargs = {key: kwargs.pop(key) for key in
                        ('include_signature', 'blockmap_omit', 'content_types_omit')
                        if key in kwargs}
        package_path = self.root / '{0}.msix'.format(rid)
        msix_fixture.write_package(package_path, files, **write_kwargs)
        return package_path

    def inspect(self, package_path, rid='win-x64', **kwargs):
        return release_tool.inspect_package(
            str(package_path), kwargs.pop('expectations', self.expectations), str(REPO_ROOT),
            rid=rid, nuget_packages=str(self.nuget), **kwargs)

    def test_well_formed_package_passes(self):
        report = self.inspect(self.write_package(), strict=True)
        self.assertEqual(release_tool.PASS, report['summary']['status'],
                         msg='\n'.join(release_tool.format_checks(report['checks'])))
        self.assertEqual('win-x64', report['architecture']['runtimeIdentifier'])
        self.assertTrue(report['package']['signed'])

    def test_inspection_records_payload_hashes(self):
        report = self.inspect(self.write_package())
        payload = {item['path']: item for item in report['payload']['files']}
        self.assertIn('PlayniteCmdPal.exe', payload)
        self.assertEqual(64, len(payload['PlayniteCmdPal.exe']['sha256']))
        self.assertGreater(report['payload']['totalBytes'], 0)

    def test_identity_mismatch_fails(self):
        package = self.write_package(manifest_overrides={'identity_name': 'Other.Package'})
        self.assertIn('manifest.identity', failing_ids(self.inspect(package)))

    def test_version_mismatch_fails(self):
        package = self.write_package(manifest_overrides={'version': '9.9.9.9'})
        self.assertIn('manifest.version', failing_ids(self.inspect(package)))

    def test_architecture_mismatch_fails(self):
        package = self.write_package(rid='win-x64', architecture='x64')
        report = self.inspect(package, rid='win-arm64')
        self.assertIn('manifest.architecture', failing_ids(report))

    def test_missing_runtime_notice_fails(self):
        package = self.write_package(drop=('dotnet-runtime-THIRD-PARTY-NOTICES.txt',))
        failures = failing_ids(self.inspect(package))
        self.assertIn('payload.runtime-notice', failures)
        self.assertIn('payload.required-files', failures)

    def test_unexpected_runtime_notice_content_fails(self):
        files = msix_fixture.package_files(str(REPO_ROOT))
        files['dotnet-runtime-THIRD-PARTY-NOTICES.txt'] = b'different runtime notice' * 3000
        package = self.root / 'tampered.msix'
        msix_fixture.write_package(package, files)
        self.assertIn('payload.runtime-notice', failing_ids(self.inspect(package)))

    def test_notice_modified_in_package_fails(self):
        package = self.write_package(payload_overrides={'LICENSE': b'not the project license'})
        self.assertIn('payload.repo-notices', failing_ids(self.inspect(package)))

    def test_missing_powertoys_notice_fails(self):
        package = self.write_package(drop=('Microsoft-PowerToys-LICENSE.txt',))
        failures = failing_ids(self.inspect(package))
        self.assertIn('payload.repo-notices', failures)
        self.assertIn('payload.required-files', failures)

    def test_dependency_tampering_fails(self):
        package = self.write_package(payload_overrides={
            'WinRT.Runtime.dll': b'not the restored CsWinRT assembly' * 64})
        self.assertIn('payload.dependency-assemblies', failing_ids(self.inspect(package)))

    def test_forbidden_test_content_fails(self):
        package = self.write_package(payload_overrides={'xunit.core.dll': b'xunit'})
        self.assertIn('payload.forbidden-content', failing_ids(self.inspect(package)))

    def test_unreviewed_content_warns_by_default_and_fails_when_strict(self):
        package = self.write_package(payload_overrides={'Unexpected.Component.dll': b'unexpected'})
        self.assertNotIn('payload.reviewed-inventory', failing_ids(self.inspect(package)))
        strict_report = self.inspect(package, strict=True)
        self.assertIn('payload.reviewed-inventory', failing_ids(strict_report))

    def test_in_process_com_registration_fails(self):
        package = self.write_package(manifest_overrides={'com_extension': 'in-process'})
        failures = failing_ids(self.inspect(package))
        self.assertIn('manifest.com-server', failures)
        self.assertIn('manifest.com-server-out-of-process', failures)

    def test_missing_visual_asset_fails(self):
        package = self.write_package(drop=('Assets/StoreLogo.png',))
        self.assertIn('payload.manifest-assets', failing_ids(self.inspect(package)))

    def test_blockmap_omission_fails(self):
        package = self.write_package(blockmap_omit=('PlayniteCmdPal.exe',))
        self.assertIn('package.blockmap', failing_ids(self.inspect(package)))

    def test_missing_content_type_fails(self):
        package = self.write_package(content_types_omit=('exe',))
        self.assertIn('package.content-types', failing_ids(self.inspect(package)))

    def test_unsigned_package_fails_by_default(self):
        package = self.write_package(include_signature=False)
        self.assertIn('package.signature', failing_ids(self.inspect(package)))

    def test_unsigned_package_is_allowed_for_presigning_inspection(self):
        package = self.write_package(include_signature=False)
        report = self.inspect(package, require_signature=False)
        self.assertNotIn('package.signature', failing_ids(report))

    def test_unresolved_manifest_token_fails(self):
        files = msix_fixture.package_files(str(REPO_ROOT))
        files['AppxManifest.xml'] = files['AppxManifest.xml'].replace(
            b'Executable="PlayniteCmdPal.exe"', b'Executable="$targetnametoken$.exe"')
        package = self.root / 'tokens.msix'
        msix_fixture.write_package(package, files)
        self.assertIn('manifest.tokens-resolved', failing_ids(self.inspect(package)))

    def test_inventory_mismatch_fails(self):
        package = self.write_package()
        inventory = {
            'schemaVersion': 1,
            'generatedAtUtc': '2026-11-17T00:00:00Z',
            'dotnetSdkVersion': '10.0.403',
            'summary': {'shipped-runtime': 4},
            'packages': [
                {'id': dependency['packageId'], 'version': dependency['version'],
                 'classification': 'shipped-runtime', 'reviewStatus': 'cleared'}
                for dependency in self.expectations['dependencyAssemblies']
            ],
        }
        inventory_path = self.root / 'inventory.json'
        inventory_path.write_text(json.dumps(inventory), encoding='utf-8')
        report = self.inspect(package, inventory=str(inventory_path))
        self.assertEqual(release_tool.PASS, report['summary']['status'],
                         msg='\n'.join(release_tool.format_checks(report['checks'])))

        inventory['packages'][0]['version'] = '0.0.0'
        inventory_path.write_text(json.dumps(inventory), encoding='utf-8')
        report = self.inspect(package, inventory=str(inventory_path))
        self.assertIn('inventory.reviewed-dependencies', failing_ids(report))

    def test_cli_inspect_exit_codes(self):
        good = self.write_package()
        self.assertEqual(0, release_tool.main(['inspect', str(good), '--repo-root', str(REPO_ROOT),
                                               '--expectations', str(self.expectations_path),
                                               '--nuget-packages', str(self.nuget),
                                               '--strict', '--rid', 'win-x64']))
        bad = self.root / 'bad.msix'
        (self.root / 'bad-dir').mkdir(exist_ok=True)
        bad.write_bytes(b'not a package')
        self.assertEqual(release_tool.EXIT_INSPECTION_FAILED,
                         release_tool.main(['inspect', str(bad), '--repo-root', str(REPO_ROOT),
                                            '--expectations', str(self.expectations_path)]))


FAKE_DOTNET = r'''#!/usr/bin/env python3
import json
import os
import shutil
import sys

args = sys.argv[1:]

PROPERTIES = {
    'TargetFramework': 'net10.0-windows10.0.26100.0',
    'WindowsSdkPackageVersion': os.environ.get('FAKE_SDK_VERSION', '10.0.26100.84'),
    'RuntimeIdentifier': os.environ.get('FAKE_RID', 'win-x64'),
    'Platform': os.environ.get('FAKE_PLATFORM', 'x64'),
    'SelfContained': 'true',
    'PublishTrimmed': 'false',
    'PublishReadyToRun': 'false',
    'PublishSingleFile': 'false',
    'AppxPackageVersion': '0.0.8.0',
    'AppxPackageIdentityName': 'werdscopez7347.PlayniteforCommandPalette',
    'AppxPackagePublisher': 'CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70',
}

if args == ['--version']:
    print('10.0.403')
    sys.exit(0)
if args[:1] == ['--list-sdks']:
    print('10.0.403 [C:\\Program Files\\dotnet\\sdk]')
    sys.exit(0)
if args[:1] == ['--list-runtimes']:
    print('Microsoft.NETCore.App 10.0.0 [C:\\Program Files\\dotnet\\shared]')
    sys.exit(0)
if args[:1] == ['msbuild']:
    properties = {}
    for argument in args:
        if argument.startswith('-getProperty:'):
            name = argument.split(':', 1)[1]
            properties[name] = PROPERTIES.get(name)
    print(json.dumps({'Properties': properties}))
    sys.exit(0)
if args[:1] in (['publish'], ['build']):
    if os.environ.get('FAKE_DOTNET_FAIL'):
        sys.stderr.write('error NETSDK0000: simulated build failure\n')
        sys.exit(1)
    appx_dir = None
    rid = None
    platform = None
    for argument in args:
        if argument.startswith('-p:AppxPackageDir='):
            appx_dir = argument.split('=', 1)[1]
        if argument.startswith('-p:Platform='):
            platform = argument.split('=', 1)[1]
        if argument == '--runtime':
            continue
    for index, argument in enumerate(args):
        if argument == '--runtime' and index + 1 < len(args):
            rid = args[index + 1]
    architecture = 'arm64' if (rid or '').endswith('arm64') else 'x64'
    source = os.path.join(os.environ['FAKE_MSIX_DIR'], architecture + '.msix')
    destination_dir = os.path.join(appx_dir, 'PlayniteCmdPal_0.0.8.0_' + architecture + '_Test')
    os.makedirs(destination_dir, exist_ok=True)
    shutil.copyfile(source, os.path.join(destination_dir, 'PlayniteCmdPal_0.0.8.0_' + architecture + '.msix'))
    print('Build succeeded for ' + str(platform))
    sys.exit(0)
sys.stderr.write('fake dotnet: unsupported arguments ' + str(args) + '\n')
sys.exit(1)
'''

FAKE_SIGNTOOL = r'''#!/usr/bin/env python3
import os
import sys

args = sys.argv[1:]
if not args:
    print('SignTool version 10.0.26100.1')
    sys.exit(1)
if os.environ.get('FAKE_SIGNTOOL_FAIL'):
    sys.stderr.write('SignTool Error: simulated signing failure\n')
    sys.exit(1)
if args[0] == 'sign':
    print('Successfully signed: ' + args[-1])
    sys.exit(0)
if args[0] == 'verify':
    print('Issued to: CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70')
    print('Successfully verified')
    sys.exit(0)
sys.stderr.write('fake signtool: unsupported arguments\n')
sys.exit(1)
'''

FAKE_MAKEAPPX = r'''#!/usr/bin/env python3
import sys
print('MakeAppx version 10.0.26100.1')
sys.exit(1)
'''


def write_executable(path, content):
    path = Path(path)
    path.write_text(content, encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


@unittest.skipIf(os.name == 'nt', 'stub executables are POSIX shell/python scripts')
class BuildOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = copy_repository_sources(self.root / 'repo')
        self.expectations_path = write_fixture_expectations(self.root / 'expectations.json')
        self.nuget = self.root / 'nuget'
        files = msix_fixture.package_files(str(REPO_ROOT))
        for package_id, version, file_name in (
                ('Microsoft.Windows.SDK.NET.Ref', '10.0.26100.84', 'Microsoft.Windows.SDK.NET.dll'),
                ('Microsoft.Windows.CsWinRT', '2.3.1', 'WinRT.Runtime.dll'),
                ('Shmuelie.WinRTServer', '2.2.1', 'Shmuelie.WinRTServer.dll'),
                ('Microsoft.CommandPalette.Extensions', '0.12.260812002',
                 'Microsoft.CommandPalette.Extensions.winmd')):
            msix_fixture.write_nuget_package(self.nuget, package_id, version, file_name, files[file_name])

        self.msix_sources = self.root / 'msix-sources'
        self.msix_sources.mkdir()
        for rid, architecture in (('win-x64', 'x64'), ('win-arm64', 'arm64')):
            package_files = msix_fixture.package_files(str(REPO_ROOT), rid=rid, architecture=architecture)
            msix_fixture.write_package(self.msix_sources / (architecture + '.msix'), package_files)

        self.fake_dotnet = write_executable(self.root / 'dotnet', FAKE_DOTNET)
        self.fake_signtool = write_executable(self.root / 'signtool', FAKE_SIGNTOOL)
        self.fake_makeappx = write_executable(self.root / 'makeappx', FAKE_MAKEAPPX)
        self.output = self.root / 'output'
        os.environ['FAKE_MSIX_DIR'] = str(self.msix_sources)

    def tearDown(self):
        os.environ.pop('FAKE_MSIX_DIR', None)
        os.environ.pop('FAKE_DOTNET_FAIL', None)
        os.environ.pop('FAKE_SIGNTOOL_FAIL', None)
        os.environ.pop('FAKE_SDK_VERSION', None)
        self.temp.cleanup()

    def build_arguments(self, extra=None):
        arguments = [
            'build',
            '--repo-root', str(self.repo),
            '--expectations', str(self.expectations_path),
            '--output', str(self.output),
            '--dotnet', str(self.fake_dotnet),
            '--signtool', str(self.fake_signtool),
            '--makeappx', str(self.fake_makeappx),
            '--nuget-packages', str(self.nuget),
            '--certificate-thumbprint', 'B5EE8A57B2274726A4E9AF40E9D47E70',
        ]
        arguments.extend(extra or [])
        return arguments

    def test_dry_run_lists_release_commands(self):
        exit_code = release_tool.main(self.build_arguments(['--dry-run']))
        self.assertEqual(0, exit_code)
        self.assertFalse(self.output.exists())

    def test_end_to_end_build_produces_passing_evidence(self):
        exit_code = release_tool.main(self.build_arguments())
        self.assertEqual(0, exit_code)

        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        self.assertEqual(release_tool.PASS, evidence['status'])
        self.assertEqual(['win-arm64', 'win-x64'],
                         sorted(package['rid'] for package in evidence['packages']))
        self.assertTrue(all(item['status'] == release_tool.PASS for item in evidence['acceptance']))

        for package in evidence['packages']:
            self.assertTrue(package['package']['signed'])
            self.assertEqual(64, len(package['package']['sha256']))
            self.assertEqual(EXPECTATIONS['package']['publisher'], package['signerSubject'])
            check_ids = {item['id']: item['status'] for item in package['inspection']['checks']}
            self.assertEqual(release_tool.PASS, check_ids['package.signature-publisher'])

        commands = [' '.join(record['command']) for record in evidence['commands']]
        self.assertTrue(any('publish' in command for command in commands))
        self.assertTrue(any('verify /pa /all /v' in command for command in commands))

        markdown = (self.output / 'evidence.md').read_text(encoding='utf-8')
        self.assertIn('PlayniteCmdPal_0.0.8.0_x64.msix', markdown)
        self.assertIn('PlayniteCmdPal_0.0.8.0_arm64.msix', markdown)
        self.assertTrue((self.output / 'SHA256SUMS').is_file())
        self.assertTrue((self.output / 'manifests/win-x64-AppxManifest.xml').is_file())

    def test_signing_is_required_by_default(self):
        arguments = self.build_arguments()
        index = arguments.index('--certificate-thumbprint')
        del arguments[index:index + 2]
        self.assertEqual(release_tool.EXIT_USAGE, release_tool.main(arguments))

    def test_unsigned_build_does_not_satisfy_acceptance(self):
        for rid, architecture in (('win-x64', 'x64'), ('win-arm64', 'arm64')):
            files = msix_fixture.package_files(str(REPO_ROOT), rid=rid, architecture=architecture)
            msix_fixture.write_package(self.msix_sources / (architecture + '.msix'), files,
                                       include_signature=False)
        arguments = self.build_arguments(['--allow-unsigned'])
        index = arguments.index('--certificate-thumbprint')
        del arguments[index:index + 2]
        exit_code = release_tool.main(arguments)
        self.assertEqual(release_tool.EXIT_INSPECTION_FAILED, exit_code)
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        self.assertEqual(release_tool.FAIL, evidence['status'])
        signed_criteria = [item for item in evidence['acceptance'] if 'signs' in item['criterion']]
        self.assertTrue(signed_criteria)
        self.assertTrue(all(item['status'] == release_tool.FAIL for item in signed_criteria))

    def test_build_failure_is_reported(self):
        os.environ['FAKE_DOTNET_FAIL'] = '1'
        self.assertEqual(release_tool.EXIT_ENVIRONMENT, release_tool.main(self.build_arguments()))

    def test_signature_verification_failure_is_reported(self):
        os.environ['FAKE_SIGNTOOL_FAIL'] = '1'
        self.assertEqual(release_tool.EXIT_ENVIRONMENT, release_tool.main(self.build_arguments()))

    def test_dirty_working_tree_blocks_release_evidence(self):
        subprocess.run(['git', 'init', '-q'], cwd=str(self.repo), check=True)
        subprocess.run(['git', 'add', '-A'], cwd=str(self.repo), check=True)
        subprocess.run(['git', '-c', 'user.email=release-tool@example.invalid',
                        '-c', 'user.name=Release Tool Self-Test', 'commit', '-q', '-m', 'fixture'],
                       cwd=str(self.repo), check=True)
        (self.repo / 'README-dirty.md').write_text('uncommitted change', encoding='utf-8')
        self.assertEqual(release_tool.EXIT_INSPECTION_FAILED, release_tool.main(self.build_arguments()))
        self.assertEqual(0, release_tool.main(self.build_arguments(['--allow-dirty'])))
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        self.assertTrue(evidence['environment']['source']['dirty'])

    def test_forced_preflight_failure_never_records_a_pass(self):
        expectations = fixture_expectations()
        expectations['source']['manifestFile'] = 'PlayniteCmdPal/missing.appxmanifest'
        broken_path = self.root / 'broken-expectations.json'
        broken_path.write_text(json.dumps(expectations, indent=2), encoding='utf-8')
        arguments = self.build_arguments(['--force'])
        index = arguments.index('--expectations')
        arguments[index + 1] = str(broken_path)
        self.assertEqual(release_tool.EXIT_INSPECTION_FAILED, release_tool.main(arguments))
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        self.assertEqual(release_tool.FAIL, evidence['status'])
        self.assertEqual(release_tool.FAIL, evidence['preflight']['status'])

    def test_unexpected_sdk_pin_blocks_the_release_build(self):
        os.environ['FAKE_SDK_VERSION'] = '10.0.26100.87'
        self.assertEqual(release_tool.EXIT_INSPECTION_FAILED, release_tool.main(self.build_arguments()))


if __name__ == '__main__':
    unittest.main()
