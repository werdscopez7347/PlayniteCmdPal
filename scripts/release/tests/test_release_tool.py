"""Self-tests for the PlayniteCmdPal release tool (scripts/release/release_tool.py).

Run from the repository root:

    python -m unittest discover -s scripts/release/tests -v

The suite is standard-library only. Inspection and preflight tests run on any
platform. Build-orchestration tests use stub dotnet/signtool executables and are
skipped on Windows because the stubs are POSIX shell scripts.
"""

import contextlib
import copy
import io
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

    def test_every_preflight_check_is_printed_once(self):
        checks = release_tool.preflight(str(REPO_ROOT), EXPECTATIONS)
        identifiers = [item['id'] for item in checks]
        self.assertEqual(len(identifiers), len(set(identifiers)),
                         msg='duplicate check ids: {0}'.format(
                             sorted({name for name in identifiers if identifiers.count(name) > 1})))
        self.assertEqual(len(checks), len(release_tool.format_checks(checks)))

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
                        ('include_signature', 'blockmap_omit', 'content_types_omit', 'blockmap_extra')
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

    def test_dependency_matches_any_copy_shipped_for_another_framework(self):
        # CsWinRT ships WinRT.Runtime.dll under several TFMs; the publish selects one, and any
        # byte-identical copy is acceptable provenance evidence.
        files = msix_fixture.package_files(str(REPO_ROOT))
        msix_fixture.write_nuget_package(self.nuget, 'Microsoft.Windows.CsWinRT', '2.3.1',
                                         'WinRT.Runtime.dll', b'a different framework build',
                                         framework='netstandard2.0')
        msix_fixture.write_nuget_package(self.nuget, 'Microsoft.Windows.CsWinRT', '2.3.1',
                                         'WinRT.Runtime.dll', files['WinRT.Runtime.dll'],
                                         framework='net8.0')
        report = self.inspect(self.write_package(), strict=True)
        self.assertEqual(release_tool.PASS, report['summary']['status'],
                         msg='\n'.join(release_tool.format_checks(report['checks'])))
        dependency = next(item for item in report['dependencyAssemblies']
                          if item['packageId'] == 'Microsoft.Windows.CsWinRT')
        self.assertEqual(2, len(dependency['packageSources']))
        self.assertTrue(dependency['identicalToPackageSource'])

    def test_forbidden_test_content_fails(self):
        package = self.write_package(payload_overrides={'xunit.core.dll': b'xunit'})
        self.assertIn('payload.forbidden-content', failing_ids(self.inspect(package)))

    def test_unreviewed_content_warns_by_default_and_fails_when_strict(self):
        package = self.write_package(payload_overrides={'Unexpected.Component.dll': b'unexpected'})
        self.assertNotIn('payload.reviewed-inventory', failing_ids(self.inspect(package)))
        strict_report = self.inspect(package, strict=True)
        self.assertIn('payload.reviewed-inventory', failing_ids(strict_report))

    def test_upper_case_manifest_language_matches_the_bcp47_expectation(self):
        # MakeAppx writes the resource language in upper case; BCP-47 tags are case-insensitive.
        package = self.write_package(manifest_overrides={'language': 'EN-US'})
        report = self.inspect(package)
        self.assertNotIn('manifest.languages', failing_ids(report))

    def test_payload_files_are_attributed_through_the_deps_manifest(self):
        # Shaped like a real self-contained publish: runtime packs are keyed with the `runtimepack.` prefix
        # and the type is declared in the libraries section.
        deps = {
            'runtimeTarget': {'name': '.NETCoreApp,Version=v10.0/win-x64'},
            'targets': {'.NETCoreApp,Version=v10.0/win-x64': {
                'Some.Package/1.2.3': {'type': 'package',
                                       'runtime': {'Some.Package.dll': {}}},
                'runtimepack.Microsoft.NETCore.App.Runtime.win-x64/10.0.14': {
                    'runtime': {
                        'System.dll': {}, 'clrgc.dll': {}, 'clrgcexp.dll': {}, 'clretwrc.dll': {},
                        'msquic.dll': {}, 'Microsoft.CSharp.dll': {}, 'System.Buffers.dll': {},
                        'Microsoft.Win32.Registry.dll': {},
                    },
                    'native': {'Microsoft.DiaSymReader.Native.amd64.dll': {}},
                },
            }},
            'libraries': {
                'Some.Package/1.2.3': {'type': 'package'},
                'runtimepack.Microsoft.NETCore.App.Runtime.win-x64/10.0.14': {'type': 'runtimepack'},
            },
        }
        payload = {
            'PlayniteCmdPal.deps.json': json.dumps(deps).encode('utf-8'),
            'Some.Package.dll': b'package-assembly',
            'System.dll': b'system-facade',
            'clrgc.dll': b'gc-implementation',
            'clrgcexp.dll': b'gc-experimental',
            'clretwrc.dll': b'runtime-resources',
            'msquic.dll': b'msquic',
            'Microsoft.CSharp.dll': b'csharp',
            'System.Buffers.dll': b'buffers',
            'Microsoft.Win32.Registry.dll': b'registry',
            'Microsoft.DiaSymReader.Native.amd64.dll': b'pdb-reader',
        }
        package = self.write_package(payload_overrides=payload)
        report = self.inspect(package, strict=True)
        # Every runtime-pack file is attributed, including the ones a reviewed pattern would also accept:
        # deps.json wins over the pattern list when it names the file.
        self.assertEqual(9, report['attribution']['runtimeFiles'])
        attributed = {item['path'] for item in report['attribution']['details']['runtime']}
        by_pattern = {item['path'] for item in report['attribution']['details']['pattern']}
        for name in ('System.Buffers.dll', 'Microsoft.CSharp.dll', 'Microsoft.Win32.Registry.dll'):
            self.assertIn(name, attributed)
            self.assertNotIn(name, by_pattern)
        self.assertTrue(by_pattern, 'the fixture still exercises the pattern fallback')
        self.assertEqual(0, report['attribution']['dependencyFiles'])
        self.assertIn('payload.reviewed-inventory', failing_ids(report))
        detail = next(check['detail'] for check in report['checks']
                      if check['id'] == 'payload.reviewed-inventory')
        self.assertIn('Some.Package 1.2.3', detail)
        self.assertIn('not in the reviewed dependency inventory', detail)

        inventory = {
            'schemaVersion': 1,
            'generatedAtUtc': '2026-11-17T00:00:00Z',
            'dotnetSdkVersion': '10.0.403',
            'summary': {'shipped-runtime': 5},
            'packages': [{'id': dependency['packageId'], 'version': dependency['version'],
                          'classification': 'shipped-runtime', 'reviewStatus': 'cleared'}
                         for dependency in self.expectations['dependencyAssemblies']]
                        + [{'id': 'Some.Package', 'version': '1.2.3',
                            'classification': 'shipped-runtime', 'reviewStatus': 'cleared'}],
        }
        inventory_path = self.root / 'deps-inventory.json'
        inventory_path.write_text(json.dumps(inventory), encoding='utf-8')
        msix_fixture.write_nuget_package(self.nuget, 'Some.Package', '1.2.3',
                                         'Some.Package.dll', b'package-assembly')
        report = self.inspect(package, strict=True, inventory=str(inventory_path))
        self.assertEqual(1, report['attribution']['dependencyFiles'])
        self.assertEqual(release_tool.PASS, report['summary']['status'],
                         msg='\n'.join(release_tool.format_checks(report['checks'])))

        # A payload file that is no copy of the reviewed package is called out by name.
        msix_fixture.write_nuget_package(self.nuget, 'Some.Package', '1.2.3',
                                         'Some.Package.dll', b'tampered')
        report = self.inspect(package, strict=True, inventory=str(inventory_path))
        detail = next(check['detail'] for check in report['checks']
                      if check['id'] == 'payload.reviewed-inventory')
        self.assertIn('does not match any copy in Some.Package 1.2.3', detail)

    def test_runtime_pack_ids_are_recognised_with_or_without_the_type_prefix(self):
        for library_id in ('runtimepack.Microsoft.NETCore.App.Runtime.win-arm64',
                           'Microsoft.NETCore.App.Runtime.win-x64',
                           'microsoft.netcore.app.runtime.linux-x64'):
            self.assertTrue(release_tool.is_runtime_library(library_id), library_id)
        self.assertTrue(release_tool.is_runtime_library('Contoso.Pack', 'runtimepack'))
        self.assertFalse(release_tool.is_runtime_library('Microsoft.CommandPalette.Extensions'))
        self.assertEqual('Microsoft.NETCore.App.Runtime.win-x64',
                         release_tool.library_display_name('runtimepack.Microsoft.NETCore.App.Runtime.win-x64'))

    def test_property_supplied_package_is_exempt_from_the_inventory(self):
        inventory = {
            'schemaVersion': 1,
            'generatedAtUtc': '2026-11-17T00:00:00Z',
            'dotnetSdkVersion': '10.0.403',
            'summary': {},
            'packages': [{'id': dependency['packageId'], 'version': dependency['version'],
                          'classification': 'shipped-runtime', 'reviewStatus': 'cleared'}
                         for dependency in self.expectations['dependencyAssemblies']
                         if dependency['packageId'] != 'Microsoft.Windows.SDK.NET.Ref'],
        }
        inventory_path = self.root / 'exempt-inventory.json'
        inventory_path.write_text(json.dumps(inventory), encoding='utf-8')
        self.expectations['inventoryExemptPackages'] = [{
            'packageId': 'Microsoft.Windows.SDK.NET.Ref',
            'reason': 'Supplied by WindowsSdkPackageVersion.',
        }]
        report = self.inspect(self.write_package(), inventory=str(inventory_path), strict=True)
        self.assertEqual(release_tool.PASS, report['summary']['status'],
                         msg='\n'.join(release_tool.format_checks(report['checks'])))

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

    def test_opc_metadata_is_not_compared_against_the_block_map(self):
        # MakeAppx lists the generated catalog in the block map; it is package metadata, not payload.
        package = self.write_package(blockmap_extra=('AppxMetadata/CodeIntegrity.cat',),
                                     payload_overrides={'AppxMetadata/CodeIntegrity.cat': b'catalog'})
        report = self.inspect(package, strict=True)
        self.assertNotIn('package.blockmap', failing_ids(report))
        self.assertNotIn('payload.reviewed-inventory', failing_ids(report))
        self.assertIn('appxmetadata/codeintegrity.cat', report['blockMap']['appxMetadataEntries'])

    def test_block_map_extra_file_is_named(self):
        package = self.write_package(blockmap_extra=('Ghost.dll',))
        report = self.inspect(package)
        detail = next(check['detail'] for check in report['checks']
                      if check['id'] == 'package.blockmap')
        self.assertIn('ghost.dll', detail)
        self.assertEqual(['ghost.dll'], report['blockMap']['extraInBlockMap'])

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
    if os.environ.get('FAKE_SIGNTOOL_BAD_PASSWORD'):
        sys.stderr.write('SignTool Error: The specified PFX password is not correct.\n')
        sys.exit(1)
    print('Successfully signed: ' + args[-1])
    sys.exit(0)
if args[0] == 'verify':
    if os.environ.get('FAKE_SIGNTOOL_UNTRUSTED'):
        sys.stderr.write('SignTool Error: A certificate chain processed, but terminated in a root '
                         'certificate which is not trusted by the trust provider. (0x800B0109)\n')
        sys.exit(1)
    print('Issued to: ' + os.environ.get('FAKE_SIGNTOOL_SUBJECT', 'B5EE8A57-B227-4726-A4E9-AF40E9D47E70'))
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


class ToolResolutionTests(unittest.TestCase):
    """Tool discovery is pure path logic, so it runs on every platform."""

    def test_signtool_is_discovered_in_the_windows_sdk_without_path(self):
        with tempfile.TemporaryDirectory() as temp:
            bin_root = Path(temp) / 'Windows Kits' / '10' / 'bin'
            for version in ('10.0.22621.0', '10.0.26100.0'):
                directory = bin_root / version / 'x64'
                directory.mkdir(parents=True, exist_ok=True)
                (directory / 'signtool.exe').write_text('stub', encoding='utf-8')
            environment = {'ProgramFiles(x86)': temp, 'PATH': ''}
            self.assertEqual(str(bin_root / '10.0.26100.0' / 'x64' / 'signtool.exe'),
                             release_tool.resolve_tool('signtool.exe', env=environment))

    def test_explicit_tool_paths_are_left_alone(self):
        self.assertEqual('/opt/tools/signtool', release_tool.resolve_tool('/opt/tools/signtool', env={'PATH': ''}))

    def test_unresolvable_tool_keeps_its_name(self):
        self.assertEqual('missing-tool.exe', release_tool.resolve_tool('missing-tool.exe', env={'PATH': ''}))


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
        os.environ.pop('FAKE_SIGNTOOL_UNTRUSTED', None)
        os.environ.pop('FAKE_SIGNTOOL_BAD_PASSWORD', None)
        os.environ.pop('FAKE_SIGNTOOL_SUBJECT', None)
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
            '--certificate-thumbprint', 'B5EE8A57B2274726A4E9AF40E9D47E70A1B2C3D4',
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
        self.assertEqual({'certificateSource': 'thumbprint', 'certificateInsideRepository': False},
                         evidence['environment']['signing'])
        self.assertEqual(['win-arm64', 'win-x64'],
                         sorted(package['rid'] for package in evidence['packages']))
        self.assertTrue(all(item['status'] == release_tool.PASS for item in evidence['acceptance']))

        for package in evidence['packages']:
            self.assertTrue(package['package']['signed'])
            self.assertEqual(64, len(package['package']['sha256']))
            # signtool prints the CN only, so compare through the same normalisation the gate uses.
            self.assertTrue(release_tool.subjects_match(
                package['signerSubject'], EXPECTATIONS['package']['publisher']))
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

    def test_unreviewed_payload_file_is_named_in_the_acceptance_detail(self):
        for rid, architecture in (('win-x64', 'x64'), ('win-arm64', 'arm64')):
            files = msix_fixture.package_files(str(REPO_ROOT), rid=rid, architecture=architecture)
            files['mystery.dll'] = b'unreviewed payload'
            msix_fixture.write_package(self.msix_sources / (architecture + '.msix'), files)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = release_tool.main(self.build_arguments())
        self.assertEqual(release_tool.EXIT_INSPECTION_FAILED, exit_code)
        self.assertIn('[FAIL] payload.reviewed-inventory', stdout.getvalue())
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        inventory_criterion = [item for item in evidence['acceptance']
                               if 'dependency inventory' in item['criterion']][0]
        self.assertEqual(release_tool.FAIL, inventory_criterion['status'])
        self.assertIn('payload.reviewed-inventory', inventory_criterion['detail'])
        self.assertIn('mystery.dll', inventory_criterion['detail'])

    def test_dirty_working_tree_blocks_release_evidence(self):
        subprocess.run(['git', 'init', '-q'], cwd=str(self.repo), check=True)
        subprocess.run(['git', 'add', '-A'], cwd=str(self.repo), check=True)
        subprocess.run(['git', '-c', 'user.email=release-tool@example.invalid',
                        '-c', 'user.name=Release Tool Self-Test', 'commit', '-q', '-m', 'fixture'],
                       cwd=str(self.repo), check=True)
        (self.repo / 'README-dirty.md').write_text('uncommitted change', encoding='utf-8')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(self.build_arguments())
        self.assertEqual(release_tool.EXIT_INSPECTION_FAILED, exit_code)
        # The operator has to be told *which* files block the run, not just that something does.
        self.assertIn('README-dirty.md', stderr.getvalue())
        self.assertEqual(0, release_tool.main(self.build_arguments(['--allow-dirty'])))
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        source = evidence['environment']['source']
        self.assertTrue(source['dirty'])
        self.assertEqual(1, source['dirtyPathCount'])
        self.assertTrue(any('README-dirty.md' in entry for entry in source['dirtyPaths']))
        markdown = (self.output / 'evidence.md').read_text(encoding='utf-8')
        self.assertIn('| Working tree dirty | yes (1 changed path) |', markdown)

    def test_dry_run_does_not_require_the_inventory_or_certificate(self):
        arguments = self.build_arguments(['--dry-run', '--inventory', str(self.root / 'missing-inventory.json')])
        index = arguments.index('--certificate-thumbprint')
        del arguments[index:index + 2]
        arguments.extend(['--certificate-pfx', str(self.root / 'missing.pfx')])
        self.assertEqual(0, release_tool.main(arguments))
        self.assertFalse(self.output.exists())

    def test_certificate_inside_the_repository_is_warned_about_and_recorded(self):
        os.environ.pop('PLAYNITECMDPAL_MSIX_PFX_PASSWORD', None)
        certificate = self.repo / 'PlayniteCmdPal-Test.pfx'
        certificate.write_bytes(b'placeholder for a real PKCS#12 blob')
        arguments = self.build_arguments()
        index = arguments.index('--certificate-thumbprint')
        del arguments[index:index + 2]
        arguments.extend(['--certificate-pfx', str(certificate)])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(arguments)
        self.assertEqual(0, exit_code)
        self.assertIn('inside the repository', stderr.getvalue())
        # Without the password the run still works, but signtool may prompt, so the operator is told.
        self.assertIn('PLAYNITECMDPAL_MSIX_PFX_PASSWORD is empty, so signtool runs without /p', stderr.getvalue())
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        signing = evidence['environment']['signing']
        self.assertEqual('pfx', signing['certificateSource'])
        self.assertTrue(signing['certificateInsideRepository'])

    def test_absent_signtool_is_reported_with_the_override(self):
        arguments = self.build_arguments()
        index = arguments.index('--signtool')
        arguments[index + 1] = 'definitely-not-signtool.exe'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(arguments)
        self.assertEqual(release_tool.EXIT_ENVIRONMENT, exit_code)
        self.assertIn('signtool was not found on PATH or in the Windows SDK', stderr.getvalue())
        self.assertIn('--signtool', stderr.getvalue())

    def test_untrusted_signing_chain_points_at_the_certificate_import(self):
        os.environ['FAKE_SIGNTOOL_UNTRUSTED'] = '1'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(self.build_arguments())
        self.assertEqual(release_tool.EXIT_ENVIRONMENT, exit_code)
        self.assertIn('Import-Certificate', stderr.getvalue())
        self.assertIn('CurrentUser', stderr.getvalue())

    def test_malformed_thumbprint_is_rejected_before_building(self):
        arguments = self.build_arguments()
        index = arguments.index('--certificate-thumbprint')
        arguments[index + 1] = '<thumbprint>'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(arguments)
        self.assertEqual(release_tool.EXIT_USAGE, exit_code)
        self.assertIn('40 hexadecimal characters', stderr.getvalue())
        self.assertFalse(self.output.exists())

    def test_thumbprint_spacing_is_normalised(self):
        arguments = self.build_arguments()
        index = arguments.index('--certificate-thumbprint')
        arguments[index + 1] = 'b5ee 8a57 b227 4726 a4e9 af40 e9d4 7e70 a1b2 c3d4'
        self.assertEqual(0, release_tool.main(arguments))
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        self.assertEqual(release_tool.PASS, evidence['status'])

    def test_subject_with_cn_prefix_also_matches(self):
        os.environ['FAKE_SIGNTOOL_SUBJECT'] = 'CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70'
        self.assertEqual(0, release_tool.main(self.build_arguments()))
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        self.assertEqual(release_tool.PASS, evidence['status'])

    def test_subject_mismatch_explains_the_identity_gate(self):
        os.environ['FAKE_SIGNTOOL_SUBJECT'] = 'PlayniteCmdPal'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(self.build_arguments())
        self.assertEqual(release_tool.EXIT_INSPECTION_FAILED, exit_code)
        self.assertIn('manifest Publisher is CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70', stderr.getvalue())
        evidence = json.loads((self.output / 'evidence.json').read_text(encoding='utf-8'))
        self.assertEqual(release_tool.FAIL, evidence['status'])

    def test_wrong_pfx_password_points_at_the_variable_and_the_thumbprint(self):
        os.environ['FAKE_SIGNTOOL_BAD_PASSWORD'] = '1'
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(self.build_arguments())
        self.assertEqual(release_tool.EXIT_ENVIRONMENT, exit_code)
        self.assertIn('PLAYNITECMDPAL_MSIX_PFX_PASSWORD', stderr.getvalue())
        self.assertIn('--certificate-thumbprint', stderr.getvalue())

    def test_missing_inventory_fails_before_any_package_is_built(self):
        arguments = self.build_arguments(['--inventory', str(self.root / 'missing-inventory.json')])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(arguments)
        self.assertEqual(release_tool.EXIT_ENVIRONMENT, exit_code)
        self.assertIn('dependency inventory', stderr.getvalue())
        self.assertIn('New-DependencyInventory.ps1', stderr.getvalue())
        self.assertFalse(self.output.exists())

    def test_missing_certificate_file_fails_before_any_package_is_built(self):
        arguments = self.build_arguments()
        index = arguments.index('--certificate-thumbprint')
        del arguments[index:index + 2]
        arguments.extend(['--certificate-pfx', str(self.root / 'missing.pfx')])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = release_tool.main(arguments)
        self.assertEqual(release_tool.EXIT_ENVIRONMENT, exit_code)
        self.assertIn('signing certificate', stderr.getvalue())
        self.assertFalse(self.output.exists())

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
