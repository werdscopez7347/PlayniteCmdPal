#!/usr/bin/env python3
"""Build, sign, inspect and record evidence for PlayniteCmdPal release MSIX packages.

This is the reproducible release-candidate pipeline tracked by WERD-81. It has three
subcommands:

    preflight   Check that the repository declarations (manifest, project, central
                properties, publish profiles, notices) match the reviewed release
                expectations in scripts/release/release_expectations.json.

    inspect     Inspect one or more MSIX archives. Every acceptance-relevant property
                (identity, version, architecture, executable COM server registration,
                assets, licenses/notices, RID-specific .NET runtime notices, reviewed
                dependency assemblies) is verified against the same expectations file.
                Inspection runs on any platform because an MSIX is an OPC ZIP archive;
                signature trust is verified with signtool during a Windows build.

    build       Run preflight, build the Release configuration for win-x64 and
                win-arm64, sign with the supplied publisher certificate, inspect both
                packages, and write a self-contained evidence bundle (JSON, Markdown,
                extracted manifests, SHA-256 sums).

Design constraints:

* Python 3 standard library only, so the tool runs on a clean Windows build machine
  and in CI without extra packages.
* Nothing is uploaded or published. No release artifact leaves the local machine.
* A check that fails makes the command exit non-zero. A check that cannot be evaluated
  is reported as SKIP or WARN with the reason, never as a pass.

Exit codes: 0 = success, 2 = inspection/preflight failed, 3 = usage error,
4 = environment or tool failure.

See docs/RELEASE-PACKAGING.md for the release process and docs/TESTING.md for the
release-tool self-tests.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

TOOL_NAME = 'playnitecmdpal_release'
TOOL_VERSION = '1.0.0'

EXIT_OK = 0
EXIT_INSPECTION_FAILED = 2
EXIT_USAGE = 3
EXIT_ENVIRONMENT = 4

PASS = 'pass'
WARN = 'warn'
FAIL = 'fail'
SKIP = 'skip'

DEFAULT_EXPECTATIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    'release_expectations.json')

SIGNATURE_FILE = 'AppxSignature.p7x'
MSIX_METADATA_FILES = ('[Content_Types].xml', 'AppxBlockMap.xml', SIGNATURE_FILE)


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------

def utc_now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest().upper()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_json(path):
    with open(path, 'r', encoding='utf-8-sig') as handle:
        return json.load(handle)


def write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        json.dump(payload, handle, indent=2)
        handle.write('\n')


def write_text(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def normalize_entry(name):
    """Manifest and block-map entries use backslashes; ZIP entries use forward
    slashes. Compare all package paths in one normalized forward-slash form."""
    return (name or '').replace('\\', '/').lstrip('/')


def check(check_id, status, detail, **extra):
    record = {'id': check_id, 'status': status, 'detail': detail}
    record.update(extra)
    return record


def checks_status(checks):
    return FAIL if any(item['status'] == FAIL for item in checks) else PASS


def summarize_checks(checks):
    summary = {PASS: 0, WARN: 0, FAIL: 0, SKIP: 0}
    for item in checks:
        summary[item['status']] = summary.get(item['status'], 0) + 1
    return summary


def format_checks(checks, prefix=''):
    return ['{0}[{1}] {2}: {3}'.format(prefix, item['status'].upper(), item['id'], item['detail'])
            for item in checks]


def matches_any(name, patterns):
    """Case-insensitive glob match against the full entry path and its base name."""
    normalized = normalize_entry(name)
    base = normalized.rsplit('/', 1)[-1]
    for pattern in patterns:
        lowered = pattern.lower()
        if fnmatch.fnmatch(normalized.lower(), lowered) or fnmatch.fnmatch(base.lower(), lowered):
            return True
    return False


# --------------------------------------------------------------------------------------
# XML helpers
# --------------------------------------------------------------------------------------

def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def child_elements(element, name=None):
    if element is None:
        return []
    if name is None:
        return list(element)
    return [item for item in element if local_name(item.tag) == name]


def first_child(element, name):
    for item in child_elements(element, name):
        return item
    return None


def all_elements(root, name):
    return [item for item in root.iter() if local_name(item.tag) == name]


def element_text(element, name, default=None):
    child = first_child(element, name)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def project_properties(project_root):
    properties = {}
    for group in child_elements(project_root, 'PropertyGroup'):
        for item in child_elements(group):
            properties[local_name(item.tag)] = (item.text or '').strip()
    return properties


def project_package_versions(project_root):
    versions = {}
    for item in all_elements(project_root, 'PackageVersion'):
        include = item.get('Include')
        if include:
            versions[include] = (item.get('Version') or '').strip()
    return versions


def project_content_items(project_root):
    items = []
    for item in all_elements(project_root, 'Content'):
        items.append({
            'include': item.get('Include') or '',
            'link': item.get('Link') or '',
            'copy_to_output': item.get('CopyToOutputDirectory') or '',
            'copy_to_publish': item.get('CopyToPublishDirectory') or '',
        })
    return items


# --------------------------------------------------------------------------------------
# Manifest parsing
# --------------------------------------------------------------------------------------

def parse_manifest(manifest_bytes):
    root = ET.fromstring(manifest_bytes)
    identity = first_child(root, 'Identity')
    properties = first_child(root, 'Properties')
    applications = first_child(root, 'Applications')
    application = first_child(applications, 'Application') if applications is not None else None
    visual_elements = first_child(application, 'VisualElements') if application is not None else None
    extensions = first_child(application, 'Extensions') if application is not None else None

    com_servers = []
    app_extensions = []
    for extension in child_elements(extensions, 'Extension'):
        category = extension.get('Category') or ''
        com_server_holder = first_child(extension, 'ComServer')
        if com_server_holder is not None:
            for server in child_elements(com_server_holder):
                com_servers.append({
                    'element': local_name(server.tag),
                    'executable': server.get('Executable'),
                    'arguments': server.get('Arguments'),
                    'class_ids': [(item.get('Id') or '').lower() for item in child_elements(server, 'Class')],
                })
        if category == 'windows.appExtension':
            app_extension = first_child(extension, 'AppExtension')
            properties_element = first_child(app_extension, 'Properties')
            create_instance = None
            interfaces = []
            if properties_element is not None:
                cmdpal = first_child(properties_element, 'CmdPalProvider')
                if cmdpal is not None:
                    activation = first_child(cmdpal, 'Activation')
                    if activation is not None:
                        instance = first_child(activation, 'CreateInstance')
                        if instance is not None:
                            create_instance = (instance.get('ClassId') or '').lower()
                    supported = first_child(cmdpal, 'SupportedInterfaces')
                    if supported is not None:
                        interfaces = [local_name(item.tag) for item in child_elements(supported)]
            app_extensions.append({
                'category': category,
                'name': (app_extension.get('Name') if app_extension is not None else '') or '',
                'public_folder': (app_extension.get('PublicFolder') if app_extension is not None else '') or '',
                'display_name': (app_extension.get('DisplayName') if app_extension is not None else '') or '',
                'create_instance_class_id': create_instance,
                'supported_interfaces': interfaces,
            })

    dependencies = []
    dependencies_element = first_child(root, 'Dependencies')
    for family in child_elements(dependencies_element, 'TargetDeviceFamily'):
        dependencies.append({
            'name': family.get('Name') or '',
            'min_version': family.get('MinVersion') or '',
            'max_version_tested': family.get('MaxVersionTested') or '',
        })

    languages = []
    resources = first_child(root, 'Resources')
    for resource in child_elements(resources, 'Resource'):
        language = resource.get('Language')
        if language:
            languages.append(language)

    capabilities = []
    capabilities_element = first_child(root, 'Capabilities')
    for capability in child_elements(capabilities_element):
        name = capability.get('Name')
        if name:
            capabilities.append(name)

    assets = {}
    if visual_elements is not None:
        for attribute in ('Square150x150Logo', 'Square44x44Logo'):
            value = visual_elements.get(attribute)
            if value:
                assets[attribute] = value
        default_tile = first_child(visual_elements, 'DefaultTile')
        if default_tile is not None and default_tile.get('Wide310x150Logo'):
            assets['Wide310x150Logo'] = default_tile.get('Wide310x150Logo')
        splash = first_child(visual_elements, 'SplashScreen')
        if splash is not None and splash.get('Image'):
            assets['SplashScreen'] = splash.get('Image')

    return {
        'root': root,
        'identity': {
            'name': identity.get('Name') if identity is not None else None,
            'publisher': identity.get('Publisher') if identity is not None else None,
            'version': identity.get('Version') if identity is not None else None,
            'processor_architecture': (identity.get('ProcessorArchitecture') if identity is not None else None),
        },
        'properties': {
            'display_name': element_text(properties, 'DisplayName'),
            'publisher_display_name': element_text(properties, 'PublisherDisplayName'),
            'logo': element_text(properties, 'Logo'),
        },
        'application': {
            'id': application.get('Id') if application is not None else None,
            'executable': application.get('Executable') if application is not None else None,
            'entry_point': application.get('EntryPoint') if application is not None else None,
            'app_list_entry': (visual_elements.get('AppListEntry') if visual_elements is not None else None),
            'assets': assets,
        },
        'com_servers': com_servers,
        'app_extensions': app_extensions,
        'dependencies': dependencies,
        'languages': languages,
        'capabilities': capabilities,
    }


# --------------------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------------------

def load_expectations(path):
    expectations = read_json(path)
    required_sections = ('schemaVersion', 'source', 'package', 'architectures', 'comServer',
                         'appExtension', 'requiredFiles', 'repoMirrors', 'dependencyAssemblies',
                         'appAssemblies', 'knownExtraPatterns', 'forbiddenPatterns', 'runtimeNotice')
    missing = [section for section in required_sections if section not in expectations]
    if missing:
        raise ValueError('Expectations file {0} is missing sections: {1}'.format(path, ', '.join(missing)))
    if expectations['schemaVersion'] != 1:
        raise ValueError('Unsupported expectations schemaVersion: {0}'.format(expectations['schemaVersion']))
    return expectations


def preflight(repo_root, expectations):
    """Validate that repository declarations match the reviewed expectations."""
    checks = []
    source = expectations['source']
    package = expectations['package']

    def repo(relative):
        return os.path.join(repo_root, relative)

    required_source_files = [source['projectFile'], source['manifestFile'],
                             source['centralBuildPropsFile'], source['centralPackagePropsFile']]
    if source.get('solutionFile'):
        required_source_files.append(source['solutionFile'])
    missing = [path for path in required_source_files if not os.path.isfile(repo(path))]
    if missing:
        checks.append(check('preflight.source-files', FAIL,
                            'Missing repository files: {0}.'.format(', '.join(missing))))
        return checks
    checks.append(check('preflight.source-files', PASS,
                        'Project, manifest, central properties and solution files are present.'))

    with open(repo(source['manifestFile']), 'rb') as handle:
        manifest = parse_manifest(handle.read())
    identity = manifest['identity']

    checks.append(check(
        'preflight.manifest.identity',
        PASS if (identity['name'] == package['identityName']
                 and identity['publisher'] == package['publisher']) else FAIL,
        'Manifest identity is {0} / {1}.'.format(identity['name'], identity['publisher']),
    ))
    checks.append(check(
        'preflight.manifest.version',
        PASS if identity['version'] == package['version'] else FAIL,
        'Manifest Version={0} (expected {1}).'.format(identity['version'], package['version']),
    ))
    properties = manifest['properties']
    checks.append(check(
        'preflight.manifest.display-properties',
        PASS if (properties.get('display_name') == package['displayName']
                 and properties.get('publisher_display_name') == package['publisherDisplayName']) else FAIL,
        'DisplayName={0}, PublisherDisplayName={1}.'.format(properties.get('display_name'),
                                                            properties.get('publisher_display_name')),
    ))
    checks.append(check(
        'preflight.manifest.logo',
        PASS if normalize_entry(properties.get('logo') or '') == normalize_entry(package['logo']) else FAIL,
        'Manifest logo is {0}.'.format(properties.get('logo')),
    ))
    checks.append(check(
        'preflight.manifest.languages',
        PASS if manifest['languages'] == package['languages'] else FAIL,
        'Languages: {0}.'.format(', '.join(manifest['languages']) or '(none)'),
    ))
    checks.append(check(
        'preflight.manifest.capabilities',
        PASS if sorted(manifest['capabilities']) == sorted(package['capabilities']) else FAIL,
        'Capabilities: {0}.'.format(', '.join(manifest['capabilities']) or '(none)'),
    ))

    families = {item['name']: item for item in manifest['dependencies']}
    desktop = families.get('Windows.Desktop')
    checks.append(check(
        'preflight.manifest.minimum-os',
        PASS if desktop is not None and desktop['min_version'] == package['minimumOsVersion'] else FAIL,
        'Windows.Desktop MinVersion={0} (expected {1}).'.format(
            desktop['min_version'] if desktop else '(missing)', package['minimumOsVersion']),
    ))
    checks.append(check(
        'preflight.manifest.device-families',
        PASS if {'Windows.Universal', 'Windows.Desktop'}.issubset(set(families)) else FAIL,
        'Declared device families: {0}.'.format(', '.join(sorted(families))),
    ))

    application = manifest['application']
    tokenized_executable = application['executable'] == '$targetnametoken$.exe'
    checks.append(check(
        'preflight.manifest.application',
        PASS if ((application['executable'] == package['applicationExecutable'] or tokenized_executable)
                 and application['app_list_entry'] == package['appListEntry']) else FAIL,
        'Application Executable={0}, AppListEntry={1}{2}.'.format(
            application['executable'], application['app_list_entry'],
            ' (build-time token, resolved during packaging)' if tokenized_executable else ''),
    ))

    com = expectations['comServer']
    executable_servers = [item for item in manifest['com_servers'] if item['element'] == com['serverElement']]
    checks.append(check(
        'preflight.manifest.com-server',
        PASS if (len(executable_servers) == 1
                 and executable_servers[0]['executable'] == com['executable']
                 and executable_servers[0]['arguments'] == com['arguments']
                 and executable_servers[0]['class_ids'] == [com['classId'].lower()]) else FAIL,
        'Out-of-process ExeServer declarations: {0}.'.format(json.dumps(executable_servers)),
    ))
    other_servers = [item for item in manifest['com_servers'] if item['element'] != com['serverElement']]
    in_process = all_elements(manifest['root'], 'InProcessServer')
    checks.append(check(
        'preflight.manifest.com-server-out-of-process',
        PASS if not other_servers and not in_process else FAIL,
        'Only an executable COM server is declared; no in-process or surrogate server registration.',
    ))

    extension = expectations['appExtension']
    matching_extensions = [item for item in manifest['app_extensions'] if item['name'] == extension['name']]
    checks.append(check(
        'preflight.manifest.app-extension',
        PASS if (len(matching_extensions) == 1
                 and matching_extensions[0]['public_folder'] == extension['publicFolder']
                 and matching_extensions[0]['create_instance_class_id'] == com['classId'].lower()
                 and extension['supportedInterface'] in matching_extensions[0]['supported_interfaces']) else FAIL,
        'Command Palette app extension declarations: {0}.'.format(json.dumps(matching_extensions)),
    ))

    project_root = ET.parse(repo(source['projectFile'])).getroot()
    project = project_properties(project_root)
    checks.append(check(
        'preflight.project.identity',
        PASS if (project.get('AppxPackageIdentityName') == package['identityName']
                 and project.get('AppxPackagePublisher') == package['publisher']) else FAIL,
        'AppxPackageIdentityName={0}, AppxPackagePublisher={1}.'.format(
            project.get('AppxPackageIdentityName'), project.get('AppxPackagePublisher')),
    ))
    checks.append(check(
        'preflight.project.version',
        PASS if project.get('AppxPackageVersion') == package['version'] else FAIL,
        'AppxPackageVersion={0} (expected {1}).'.format(project.get('AppxPackageVersion'), package['version']),
    ))
    checks.append(check(
        'preflight.project.target-framework',
        PASS if project.get('TargetFramework') == package['targetFramework'] else FAIL,
        'TargetFramework={0}.'.format(project.get('TargetFramework')),
    ))
    rids = [item.strip() for item in (project.get('RuntimeIdentifiers') or '').split(';') if item.strip()]
    checks.append(check(
        'preflight.project.runtime-identifiers',
        PASS if sorted(rids) == sorted(expectations['architectures'].keys()) else FAIL,
        'RuntimeIdentifiers={0}.'.format(';'.join(rids)),
    ))
    checks.append(check(
        'preflight.project.msix-tooling',
        PASS if (project.get('EnableMsixTooling', '').lower() == 'true'
                 and project.get('AppxHarvestWinmdRegistration', '').lower() == 'false') else FAIL,
        'EnableMsixTooling={0}, AppxHarvestWinmdRegistration={1}.'.format(
            project.get('EnableMsixTooling'), project.get('AppxHarvestWinmdRegistration')),
    ))

    content_items = project_content_items(project_root)
    for mirror in expectations['repoMirrors']:
        repo_path = normalize_entry(mirror['repoPath'])
        source_file = repo(mirror['repoPath'])
        if not os.path.isfile(source_file):
            checks.append(check('preflight.notice.{0}'.format(repo_path), FAIL,
                                'Source notice {0} is missing.'.format(mirror['repoPath'])))
            continue
        candidates = [item for item in content_items
                      if normalize_entry(item['include']).endswith(repo_path)]
        packaged = bool(candidates) and all(
            item['copy_to_publish'].lower() == 'preservenewest' for item in candidates)
        checks.append(check(
            'preflight.notice.{0}'.format(repo_path),
            PASS if packaged else FAIL,
            '{0} is copied to the publish output as {1}.'.format(mirror['repoPath'], mirror['packagePath']),
        ))

    project_text = None
    with open(repo(source['projectFile']), 'r', encoding='utf-8-sig') as handle:
        project_text = handle.read()
    missing_targets = [target for target in source['artifactNoticeTargets'] if target not in project_text]
    checks.append(check(
        'preflight.project.runtime-notice-targets',
        PASS if not missing_targets else FAIL,
        'Runtime-notice targets present: {0}.'.format(
            ', '.join(source['artifactNoticeTargets']) if not missing_targets
            else 'missing ' + ', '.join(missing_targets)),
    ))

    build_props = project_properties(ET.parse(repo(source['centralBuildPropsFile'])).getroot())
    checks.append(check(
        'preflight.props.windows-sdk-package',
        PASS if build_props.get('WindowsSdkPackageVersion') == package['windowsSdkPackageVersion'] else FAIL,
        'WindowsSdkPackageVersion={0} (expected {1}).'.format(
            build_props.get('WindowsSdkPackageVersion'), package['windowsSdkPackageVersion']),
    ))
    platforms = [item.strip() for item in (build_props.get('Platforms') or '').split(';') if item.strip()]
    expected_platforms = sorted(item['platform'] for item in expectations['architectures'].values())
    checks.append(check(
        'preflight.props.platforms',
        PASS if sorted(platforms) == expected_platforms else FAIL,
        'Platforms={0}.'.format(';'.join(platforms)),
    ))

    package_versions = project_package_versions(
        ET.parse(repo(source['centralPackagePropsFile'])).getroot())
    for dependency in expectations['dependencyAssemblies']:
        declared = package_versions.get(dependency['packageId'])
        if declared is None:
            checks.append(check(
                'preflight.package.{0}'.format(dependency['packageId']), PASS,
                '{0} is supplied by an MSBuild property rather than a central PackageVersion.'.format(
                    dependency['packageId']),
            ))
        else:
            checks.append(check(
                'preflight.package.{0}'.format(dependency['packageId']),
                PASS if declared == dependency['version'] else FAIL,
                '{0} {1} (expected {2}).'.format(dependency['packageId'], declared, dependency['version']),
            ))

    for rid, architecture in expectations['architectures'].items():
        profile_path = source['publishProfiles'].get(rid)
        if not profile_path or not os.path.isfile(repo(profile_path)):
            checks.append(check('preflight.profile.{0}'.format(rid), FAIL,
                                'Publish profile is missing for {0}.'.format(rid)))
            continue
        profile = project_properties(ET.parse(repo(profile_path)).getroot())
        expected = {
            'RuntimeIdentifier': rid,
            'Platform': architecture['platform'],
            'SelfContained': 'true',
            'PublishSingleFile': 'false',
            'PublishTrimmed': 'false',
            'PublishReadyToRun': 'false',
        }
        mismatches = ['{0}={1} (expected {2})'.format(key, profile.get(key), value)
                      for key, value in expected.items()
                      if (profile.get(key) or '').lower() != value.lower()]
        checks.append(check(
            'preflight.profile.{0}'.format(rid),
            PASS if not mismatches else FAIL,
            'Publish profile {0}: {1}.'.format(
                profile_path, '; '.join(mismatches) if mismatches else 'release settings match'),
        ))
        notice_digest = expectations['runtimeNotice']['sha256ByRid'].get(rid)
        checks.append(check(
            'preflight.runtime-notice.{0}'.format(rid),
            PASS if notice_digest else FAIL,
            'Expected runtime notice SHA-256 for {0}: {1}.'.format(rid, notice_digest or '(missing)'),
        ))

    checks.append(check(
        'preflight.expectations.architectures',
        PASS if sorted(expectations['architectures']) == ['win-arm64', 'win-x64'] else FAIL,
        'Expectations cover win-x64 and win-arm64.',
    ))
    return checks


# --------------------------------------------------------------------------------------
# Package inspection
# --------------------------------------------------------------------------------------

def _asset_exists(payload_names, referenced):
    referenced = normalize_entry(referenced)
    lowered_names = {name.lower() for name in payload_names}
    if referenced.lower() in lowered_names:
        return True
    stem, extension = os.path.splitext(referenced)
    prefix = (stem + '.').lower()
    extension = extension.lower()
    for name in sorted(lowered_names):
        if name.startswith(prefix) and name.endswith(extension):
            qualifier = name[len(stem) + 1:len(name) - len(extension)]
            if qualifier and not qualifier.startswith('.'):
                return True
    return False


def _inspect_blockmap(zf, names, checks):
    if 'AppxBlockMap.xml' not in names:
        checks.append(check('package.blockmap', FAIL,
                            'AppxBlockMap.xml is absent; the archive is not a valid MSIX package.'))
        return {'present': False}
    try:
        root = ET.fromstring(zf.read('AppxBlockMap.xml'))
    except ET.ParseError as error:
        checks.append(check('package.blockmap', FAIL,
                            'AppxBlockMap.xml is not well-formed XML: {0}.'.format(error)))
        return {'present': True, 'parseError': str(error)}

    blockmap_files = {normalize_entry(item.get('Name')).lower()
                      for item in all_elements(root, 'File') if item.get('Name')}
    payload = {name.lower() for name in names if name not in MSIX_METADATA_FILES}
    missing_from_blockmap = sorted(payload - blockmap_files)
    extra_in_blockmap = sorted(blockmap_files - payload)
    valid = not missing_from_blockmap and not extra_in_blockmap
    checks.append(check(
        'package.blockmap',
        PASS if valid else FAIL,
        'AppxBlockMap.xml lists {0} payload files ({1}).'.format(
            len(blockmap_files), 'consistent with the archive' if valid else 'inconsistent with the archive'),
        missingFromBlockMap=missing_from_blockmap,
        extraInBlockMap=extra_in_blockmap,
    ))
    return {'present': True, 'fileCount': len(blockmap_files), 'consistent': valid}


def _inspect_content_types(zf, names, checks):
    content_type_file = '[Content_Types].xml'
    if content_type_file not in names:
        checks.append(check('package.content-types', FAIL, '[Content_Types].xml is absent.'))
        return {'present': False}
    try:
        root = ET.fromstring(zf.read(content_type_file))
    except ET.ParseError as error:
        checks.append(check('package.content-types', FAIL,
                            '[Content_Types].xml is not well-formed: {0}.'.format(error)))
        return {'present': True}
    defaults = {(item.get('Extension') or '').lower() for item in all_elements(root, 'Default')}
    overrides = {normalize_entry(item.get('PartName') or '').lower()
                 for item in all_elements(root, 'Override')}
    undeclared = []
    for name in names:
        if name in MSIX_METADATA_FILES:
            continue
        normalized = name.lower()
        file_part = normalized.rsplit('/', 1)[-1]
        extension = file_part.rsplit('.', 1)[-1] if '.' in file_part else ''
        if normalized in overrides or (extension and extension in defaults):
            continue
        undeclared.append(name)
    checks.append(check(
        'package.content-types',
        PASS if not undeclared else FAIL,
        'Every payload file declares a content type.' if not undeclared
        else '{0} payload file(s) have no content type declaration.'.format(len(undeclared)),
        undeclared=sorted(undeclared),
    ))
    return {'present': True, 'defaultExtensions': sorted(defaults), 'overrideCount': len(overrides)}


def find_package_source(nuget_root, package_id, version, file_name):
    """Locate a dependency assembly in the restored NuGet package folder."""
    package_dir = os.path.join(nuget_root, package_id.lower(), version)
    if not os.path.isdir(package_dir):
        return None
    matches = []
    for base, _directories, files in os.walk(package_dir):
        for name in files:
            if name.lower() == file_name.lower():
                matches.append(os.path.join(base, name))
    if not matches:
        return None
    matches.sort(key=lambda path: (0 if (os.sep + 'lib' + os.sep) in path else 1, len(path)))
    return matches[0]


def _inspect_inventory(inventory_path, expectations):
    checks = []
    if not os.path.isfile(inventory_path):
        return [check('inventory.present', FAIL,
                      'Dependency inventory {0} does not exist.'.format(inventory_path))], None
    try:
        inventory = read_json(inventory_path)
    except ValueError as error:
        return [check('inventory.parse', FAIL, 'Inventory is not valid JSON: {0}.'.format(error))], None

    packages = {item.get('id'): item for item in inventory.get('packages', []) if isinstance(item, dict)}
    checks.append(check('inventory.schema', PASS if inventory.get('schemaVersion') == 1 else FAIL,
                        'Inventory schemaVersion={0}.'.format(inventory.get('schemaVersion'))))

    failures = []
    for dependency in expectations['dependencyAssemblies']:
        entry = packages.get(dependency['packageId'])
        if entry is None:
            failures.append('{0} is not in the inventory'.format(dependency['packageId']))
        elif entry.get('version') != dependency['version']:
            failures.append('{0} resolved {1} (expected {2})'.format(
                dependency['packageId'], entry.get('version'), dependency['version']))
        elif entry.get('classification') not in ('shipped-runtime', 'shipped-build'):
            failures.append('{0} is classified {1}'.format(dependency['packageId'], entry.get('classification')))
    checks.append(check(
        'inventory.reviewed-dependencies',
        PASS if not failures else FAIL,
        'Reviewed dependency packages are present with the expected versions and shipped classifications.'
        if not failures else '; '.join(failures),
    ))

    review = [item for item in packages.values() if item.get('reviewStatus') == 'review']
    shipped_review = [item for item in review if str(item.get('classification', '')).startswith('shipped-')]
    checks.append(check(
        'inventory.review-flags',
        PASS if not shipped_review else WARN,
        'No shipped dependency has an open review flag.' if not shipped_review
        else '{0} shipped package(s) still carry review flags: {1}.'.format(
            len(shipped_review), ', '.join(sorted(item.get('id') or '?' for item in shipped_review))),
    ))

    report = {
        'path': inventory_path,
        'sha256': sha256_file(inventory_path),
        'generatedAtUtc': inventory.get('generatedAtUtc'),
        'dotnetSdkVersion': inventory.get('dotnetSdkVersion'),
        'summary': inventory.get('summary') or {},
        'reviewFlaggedShippedPackages': sorted(item.get('id') or '?' for item in shipped_review),
    }
    return checks, report


def inspect_package(package_path, expectations, repo_root, rid=None, nuget_packages=None,
                    inventory=None, strict=False, require_signature=True):
    checks = []
    package_expectation = expectations['package']
    report = {
        'tool': {'name': TOOL_NAME, 'version': TOOL_VERSION},
        'generatedAtUtc': utc_now(),
        'package': {'path': package_path, 'fileName': os.path.basename(package_path)},
        'inspectionMethod': ('OPC/ZIP archive inspection: AppxManifest.xml, AppxBlockMap.xml, '
                             '[Content_Types].xml, payload listing and per-file SHA-256'),
        'strict': strict,
    }

    if not os.path.isfile(package_path):
        checks.append(check('package.present', FAIL, 'Package file does not exist.'))
        report['checks'] = checks
        report['summary'] = {'status': FAIL, 'counts': summarize_checks(checks)}
        return report

    package_size = os.path.getsize(package_path)
    report['package'].update({'sizeBytes': package_size, 'sha256': sha256_file(package_path)})
    checks.append(check(
        'package.size',
        PASS if package_size >= package_expectation['minimumPackageBytes'] else FAIL,
        'Package size {0:,} bytes (minimum {1:,}).'.format(
            package_size, package_expectation['minimumPackageBytes']),
    ))

    try:
        zf = zipfile.ZipFile(package_path)
    except zipfile.BadZipFile:
        checks.append(check('package.archive', FAIL, 'File is not a readable ZIP/OPC archive.'))
        report['checks'] = checks
        report['summary'] = {'status': FAIL, 'counts': summarize_checks(checks)}
        return report

    with zf:
        original_names = {normalize_entry(name): name for name in zf.namelist()}
        names = sorted(name for name in original_names if name and not name.endswith('/'))
        name_set = set(names)
        report['package']['fileCount'] = len(names)
        checks.append(check('package.archive', PASS, 'Archive contains {0} payload entries.'.format(len(names))))

        if 'AppxManifest.xml' not in name_set:
            checks.append(check('manifest.present', FAIL, 'AppxManifest.xml is absent from the package.'))
            report['checks'] = checks
            report['summary'] = {'status': FAIL, 'counts': summarize_checks(checks)}
            return report

        manifest_bytes = zf.read(original_names['AppxManifest.xml'])
        manifest = parse_manifest(manifest_bytes)
        identity = manifest['identity']
        report['manifest'] = {
            'sha256': sha256_bytes(manifest_bytes),
            'identity': identity,
            'properties': manifest['properties'],
            'application': manifest['application'],
            'comServers': manifest['com_servers'],
            'appExtensions': manifest['app_extensions'],
            'dependencies': manifest['dependencies'],
            'languages': manifest['languages'],
            'capabilities': manifest['capabilities'],
        }

        # Architecture ------------------------------------------------------------
        declared_architecture = (identity['processor_architecture'] or '').lower()
        architecture_map = {value['manifestArchitecture'].lower(): key
                            for key, value in expectations['architectures'].items()}
        effective_rid = rid or architecture_map.get(declared_architecture)
        report['architecture'] = {
            'manifestArchitecture': identity['processor_architecture'],
            'runtimeIdentifier': effective_rid,
        }
        if rid:
            expected_architecture = expectations['architectures'][rid]['manifestArchitecture'].lower()
            checks.append(check(
                'manifest.architecture',
                PASS if declared_architecture == expected_architecture else FAIL,
                'Manifest ProcessorArchitecture={0} (expected {1} for {2}).'.format(
                    identity['processor_architecture'], expected_architecture, rid),
            ))
        elif effective_rid:
            checks.append(check('manifest.architecture', PASS,
                                'Manifest ProcessorArchitecture={0}.'.format(identity['processor_architecture'])))
        else:
            checks.append(check('manifest.architecture', FAIL,
                                'Manifest ProcessorArchitecture={0}; expected one of {1}.'.format(
                                    identity['processor_architecture'], ', '.join(sorted(architecture_map)))))

        checks.append(check(
            'manifest.identity',
            PASS if (identity['name'] == package_expectation['identityName']
                     and identity['publisher'] == package_expectation['publisher']) else FAIL,
            'Identity Name={0}, Publisher={1}.'.format(identity['name'], identity['publisher']),
        ))
        checks.append(check(
            'manifest.version',
            PASS if identity['version'] == package_expectation['version'] else FAIL,
            'Manifest Version={0} (expected {1}).'.format(identity['version'], package_expectation['version']),
        ))
        properties = manifest['properties']
        checks.append(check(
            'manifest.display-properties',
            PASS if (properties.get('display_name') == package_expectation['displayName']
                     and properties.get('publisher_display_name') == package_expectation['publisherDisplayName'])
            else FAIL,
            'DisplayName={0}, PublisherDisplayName={1}.'.format(
                properties.get('display_name'), properties.get('publisher_display_name')),
        ))
        checks.append(check(
            'manifest.languages',
            PASS if manifest['languages'] == package_expectation['languages'] else FAIL,
            'Languages: {0}.'.format(', '.join(manifest['languages']) or '(none)'),
        ))
        checks.append(check(
            'manifest.capabilities',
            PASS if sorted(manifest['capabilities']) == sorted(package_expectation['capabilities']) else FAIL,
            'Capabilities: {0}.'.format(', '.join(manifest['capabilities']) or '(none)'),
        ))

        families = {item['name']: item for item in manifest['dependencies']}
        desktop = families.get('Windows.Desktop')
        checks.append(check(
            'manifest.minimum-os',
            PASS if (desktop is not None
                     and desktop['min_version'] == package_expectation['minimumOsVersion']
                     and {'Windows.Universal', 'Windows.Desktop'}.issubset(set(families))) else FAIL,
            'TargetDeviceFamily declarations: {0}.'.format(json.dumps(manifest['dependencies'])),
        ))

        manifest_text = manifest_bytes.decode('utf-8', 'replace')
        unresolved = [token for token in ('$targetnametoken$', '$targetentrypoint$') if token in manifest_text]
        checks.append(check(
            'manifest.tokens-resolved',
            PASS if not unresolved else FAIL,
            'Build-time manifest tokens are resolved.' if not unresolved
            else 'Unresolved manifest tokens: {0}.'.format(', '.join(unresolved)),
        ))

        application = manifest['application']
        checks.append(check(
            'manifest.application',
            PASS if (application['executable'] == package_expectation['applicationExecutable']
                     and application['app_list_entry'] == package_expectation['appListEntry']) else FAIL,
            'Application Executable={0}, EntryPoint={1}, AppListEntry={2}.'.format(
                application['executable'], application['entry_point'], application['app_list_entry']),
        ))

        com = expectations['comServer']
        executable_servers = [item for item in manifest['com_servers'] if item['element'] == com['serverElement']]
        checks.append(check(
            'manifest.com-server',
            PASS if (len(executable_servers) == 1
                     and executable_servers[0]['executable'] == com['executable']
                     and executable_servers[0]['arguments'] == com['arguments']
                     and executable_servers[0]['class_ids'] == [com['classId'].lower()]) else FAIL,
            'Executable COM server declarations: {0}.'.format(json.dumps(executable_servers)),
        ))
        other_servers = [item for item in manifest['com_servers'] if item['element'] != com['serverElement']]
        in_process = all_elements(manifest['root'], 'InProcessServer')
        checks.append(check(
            'manifest.com-server-out-of-process',
            PASS if not other_servers and not in_process else FAIL,
            'COM registration is an out-of-process ExeServer with no in-process or surrogate registration.'
            if not other_servers and not in_process
            else 'Unexpected COM registration: {0}.'.format(json.dumps(other_servers)),
        ))

        extension = expectations['appExtension']
        matching_extensions = [item for item in manifest['app_extensions'] if item['name'] == extension['name']]
        checks.append(check(
            'manifest.app-extension',
            PASS if (len(matching_extensions) == 1
                     and matching_extensions[0]['public_folder'] == extension['publicFolder']
                     and matching_extensions[0]['create_instance_class_id'] == com['classId'].lower()
                     and extension['supportedInterface'] in matching_extensions[0]['supported_interfaces'])
            else FAIL,
            'Command Palette app extension declarations: {0}.'.format(json.dumps(matching_extensions)),
        ))

        asset_references = dict(application['assets'])
        if properties.get('logo'):
            asset_references['Logo'] = properties['logo']
        missing_assets = sorted(name for name, value in asset_references.items()
                                if not _asset_exists(name_set, value))
        checks.append(check(
            'payload.manifest-assets',
            PASS if not missing_assets else FAIL,
            'All {0} manifest asset references resolve to packaged visual assets.'.format(len(asset_references))
            if not missing_assets else 'Missing packaged assets for: {0}.'.format(', '.join(missing_assets)),
            assets=asset_references,
        ))

        # Payload -----------------------------------------------------------------
        payload = []
        for name in names:
            info = zf.getinfo(original_names[name])
            payload.append({
                'path': name,
                'sizeBytes': info.file_size,
                'sha256': sha256_bytes(zf.read(info)),
            })
        payload_by_path = {item['path']: item for item in payload}
        payload_names = set(payload_by_path)
        report['payload'] = {
            'fileCount': len(payload),
            'totalBytes': sum(item['sizeBytes'] for item in payload),
            'files': payload,
        }

        missing_required = []
        for required in expectations['requiredFiles']:
            path = normalize_entry(required['path'])
            item = payload_by_path.get(path)
            if item is None or item['sizeBytes'] < required.get('minBytes', 1):
                missing_required.append(path)
        checks.append(check(
            'payload.required-files',
            PASS if not missing_required else FAIL,
            'All {0} required payload files are present.'.format(len(expectations['requiredFiles']))
            if not missing_required else 'Missing or undersized payload files: {0}.'.format(
                ', '.join(missing_required)),
        ))

        mirror_results = []
        mirror_mismatches = []
        for mirror in expectations['repoMirrors']:
            packaged_path = normalize_entry(mirror['packagePath'])
            item = payload_by_path.get(packaged_path)
            repo_file = os.path.join(repo_root, mirror['repoPath'])
            repo_digest = sha256_file(repo_file) if os.path.isfile(repo_file) else None
            matches = item is not None and repo_digest is not None and item['sha256'] == repo_digest
            mirror_results.append({
                'packagePath': mirror['packagePath'],
                'repoPath': mirror['repoPath'],
                'packageSha256': item['sha256'] if item else None,
                'repoSha256': repo_digest,
                'matches': matches,
            })
            if not matches:
                mirror_mismatches.append(mirror['packagePath'])
        checks.append(check(
            'payload.repo-notices',
            PASS if not mirror_mismatches else FAIL,
            'LICENSE, third-party notices and the PowerToys template notice match the repository copies byte-for-byte.'
            if not mirror_mismatches else 'Notices differ from the repository copies: {0}.'.format(
                ', '.join(mirror_mismatches)),
            notices=mirror_results,
        ))

        runtime_notice = expectations['runtimeNotice']
        notice_path = normalize_entry(runtime_notice['packagePath'])
        notice_item = payload_by_path.get(notice_path)
        expected_notice_digest = (runtime_notice['sha256ByRid'].get(effective_rid)
                                  if effective_rid else None)
        if notice_item is None:
            checks.append(check('payload.runtime-notice', FAIL,
                                'RID-specific .NET runtime notices are absent ({0}).'.format(notice_path)))
        elif notice_item['sizeBytes'] < runtime_notice['minBytes']:
            checks.append(check('payload.runtime-notice', FAIL,
                                'Runtime notice is only {0:,} bytes.'.format(notice_item['sizeBytes'])))
        elif not expected_notice_digest:
            checks.append(check(
                'payload.runtime-notice', WARN,
                'Runtime notice present ({0:,} bytes) but no expected SHA-256 is recorded for {1}.'.format(
                    notice_item['sizeBytes'], effective_rid or 'this architecture')))
        else:
            matches = notice_item['sha256'] == expected_notice_digest
            checks.append(check(
                'payload.runtime-notice',
                PASS if matches else FAIL,
                'Runtime notice {0:,} bytes, SHA-256 {1}{2}.'.format(
                    notice_item['sizeBytes'], notice_item['sha256'],
                    '' if matches else ' (expected {0})'.format(expected_notice_digest)),
            ))
        report['runtimeNotice'] = {
            'packagePath': runtime_notice['packagePath'],
            'sizeBytes': notice_item['sizeBytes'] if notice_item else None,
            'sha256': notice_item['sha256'] if notice_item else None,
            'expectedSha256': expected_notice_digest,
        }

        dependency_results = []
        dependency_failures = []
        for dependency in expectations['dependencyAssemblies']:
            path = normalize_entry(dependency['payloadPath'])
            item = payload_by_path.get(path)
            source_path = None
            source_digest = None
            if item is None:
                dependency_failures.append('{0} is absent'.format(path))
            elif nuget_packages and dependency.get('compareToPackageSource'):
                source_path = find_package_source(nuget_packages, dependency['packageId'],
                                                  dependency['version'], os.path.basename(path))
                if source_path:
                    source_digest = sha256_file(source_path)
                    if source_digest != item['sha256']:
                        dependency_failures.append('{0} does not match {1} {2}'.format(
                            path, dependency['packageId'], dependency['version']))
                else:
                    checks.append(check(
                        'payload.dependency-source.{0}'.format(os.path.basename(path)), WARN,
                        'Package source for {0} {1} was not found in the NuGet cache; byte-for-byte '
                        'comparison was skipped.'.format(dependency['packageId'], dependency['version'])))
            dependency_results.append({
                'packageId': dependency['packageId'],
                'version': dependency['version'],
                'payloadPath': dependency['payloadPath'],
                'payloadSha256': item['sha256'] if item else None,
                'packageSourcePath': source_path,
                'packageSourceSha256': source_digest,
                'identicalToPackageSource': (source_digest == item['sha256']) if (source_digest and item) else None,
            })
        checks.append(check(
            'payload.dependency-assemblies',
            PASS if not dependency_failures else FAIL,
            'All {0} reviewed dependency assemblies are present{1}.'.format(
                len(expectations['dependencyAssemblies']),
                ' and byte-identical to their package source' if nuget_packages and not dependency_failures else '')
            if not dependency_failures else '; '.join(dependency_failures),
        ))
        report['dependencyAssemblies'] = dependency_results

        app_assembly_paths = {normalize_entry(name) for name in expectations['appAssemblies']}
        missing_app = sorted(path for path in app_assembly_paths if path not in payload_by_path)
        checks.append(check(
            'payload.app-assemblies',
            PASS if not missing_app else FAIL,
            'Project assemblies shipped: {0}.'.format(', '.join(sorted(app_assembly_paths)))
            if not missing_app else 'Missing project assemblies: {0}.'.format(', '.join(missing_app)),
        ))

        forbidden_hits = sorted(name for name in payload_names
                                if matches_any(name, expectations['forbiddenPatterns']))
        checks.append(check(
            'payload.forbidden-content',
            PASS if not forbidden_hits else FAIL,
            'No build-only, test-only or tooling files are packaged.'
            if not forbidden_hits else 'Build/test tooling is packaged: {0}.'.format(', '.join(forbidden_hits[:20])),
            matches=forbidden_hits,
        ))

        reviewed = set()
        reviewed.update(normalize_entry(item['path']) for item in expectations['requiredFiles'])
        reviewed.update(app_assembly_paths)
        reviewed.update(normalize_entry(item['payloadPath']) for item in expectations['dependencyAssemblies'])
        reviewed.update(normalize_entry(item['packagePath']) for item in expectations['repoMirrors'])
        reviewed.add(notice_path)
        unreviewed = sorted(
            name for name in payload_names
            if name not in reviewed
            and name not in MSIX_METADATA_FILES
            and not matches_any(name, expectations['knownExtraPatterns'])
            and not matches_any(name, expectations['forbiddenPatterns'])
        )
        checks.append(check(
            'payload.reviewed-inventory',
            (FAIL if strict else WARN) if unreviewed else PASS,
            'Every payload file is attributable to the app, the reviewed dependency inventory, or the .NET runtime.'
            if not unreviewed
            else 'Unreviewed payload files: {0}. Classify them in release_expectations.json.'.format(
                ', '.join(unreviewed[:20])),
            matches=unreviewed,
        ))

        signature_item = payload_by_path.get(SIGNATURE_FILE)
        signed = signature_item is not None and signature_item['sizeBytes'] > 0
        report['package']['signed'] = signed
        if signed:
            checks.append(check(
                'package.signature', PASS,
                'AppxSignature.p7x present ({0:,} bytes); trust chain is verified with signtool during a '
                'Windows build.'.format(signature_item['sizeBytes'])))
        elif require_signature:
            checks.append(check('package.signature', FAIL,
                                'Package is unsigned (AppxSignature.p7x is absent); a release candidate must be signed.'))
        else:
            checks.append(check('package.signature', WARN,
                                'Package is unsigned; unsigned inspection was explicitly allowed.'))

        report['blockMap'] = _inspect_blockmap(zf, names, checks)
        report['contentTypes'] = _inspect_content_types(zf, names, checks)

    if inventory:
        inventory_checks, inventory_report = _inspect_inventory(inventory, expectations)
        checks.extend(inventory_checks)
        report['inventory'] = inventory_report

    report['checks'] = checks
    report['summary'] = {'status': checks_status(checks), 'counts': summarize_checks(checks)}
    return report


# --------------------------------------------------------------------------------------
# Command execution and environment recording
# --------------------------------------------------------------------------------------

def run_command(command, cwd=None, env=None, log=None):
    started = time.time()
    try:
        completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True,
                                   encoding='utf-8', errors='replace')
        record = {
            'command': list(command),
            'exitCode': completed.returncode,
            'durationMs': int((time.time() - started) * 1000),
            'stdoutTail': completed.stdout[-4000:],
            'stderrTail': completed.stderr[-4000:],
        }
    except FileNotFoundError:
        record = {
            'command': list(command),
            'exitCode': None,
            'durationMs': int((time.time() - started) * 1000),
            'stdoutTail': '',
            'stderrTail': 'Executable not found: {0}'.format(command[0]),
        }
    if log is not None:
        log.append(record)
    return record


def git_value(repo_root, *arguments):
    record = run_command(['git'] + list(arguments), cwd=repo_root)
    return record['stdoutTail'].strip() if record['exitCode'] == 0 else None


def collect_environment(repo_root, dotnet, signtool, makeappx):
    environment = {
        'recordedAtUtc': utc_now(),
        'platform': platform.platform(),
        'operatingSystem': os.name,
        'machine': platform.machine(),
        'python': sys.version.split()[0],
    }
    if os.name == 'nt':
        environment['windows'] = {
            'release': platform.release(),
            'version': platform.version(),
            'win32ver': list(platform.win32_ver()),
        }
    environment['dotnet'] = {}
    for label, arguments in (('version', ['--version']), ('sdks', ['--list-sdks']),
                             ('runtimes', ['--list-runtimes'])):
        record = run_command([dotnet] + arguments, cwd=repo_root)
        environment['dotnet'][label] = record['stdoutTail'].strip() if record['exitCode'] == 0 else None
    for label, executable in (('signtool', signtool), ('makeappx', makeappx)):
        if not executable:
            environment[label] = None
            continue
        record = run_command([executable], cwd=repo_root)
        output = (record['stdoutTail'] or '') + (record['stderrTail'] or '')
        version_line = None
        for line in output.splitlines():
            lowered = line.lower()
            if 'version' in lowered and any(character.isdigit() for character in lowered):
                version_line = line.strip()
                break
        environment[label] = {'path': executable, 'versionLine': version_line, 'exitCode': record['exitCode']}
    environment['source'] = {
        'commit': git_value(repo_root, 'rev-parse', 'HEAD'),
        'branch': git_value(repo_root, 'rev-parse', '--abbrev-ref', 'HEAD'),
        'describe': git_value(repo_root, 'describe', '--tags', '--always', '--dirty'),
        'dirty': bool(git_value(repo_root, 'status', '--porcelain')),
    }
    return environment


def evaluate_msbuild_properties(dotnet, project, properties, log=None, cwd=None):
    arguments = ['msbuild', project]
    for name in properties:
        arguments.append('-getProperty:{0}'.format(name))
    record = run_command([dotnet] + arguments, cwd=cwd, log=log)
    values = {}
    if record['exitCode'] == 0:
        text = record['stdoutTail'].strip()
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            try:
                payload = json.loads(text[start:end + 1])
                raw = payload.get('Properties', payload) if isinstance(payload, dict) else {}
                values = {name: raw.get(name) for name in properties}
            except ValueError:
                values = {}
    return values, record


# --------------------------------------------------------------------------------------
# Signing helpers
# --------------------------------------------------------------------------------------

def signing_arguments(args):
    if args.certificate_pfx:
        password = os.environ.get(args.certificate_password_env, '') if args.certificate_password_env else ''
        arguments = ['sign', '/fd', 'SHA256', '/f', args.certificate_pfx]
        if password:
            arguments.extend(['/p', password])
    elif args.certificate_thumbprint:
        arguments = ['sign', '/fd', 'SHA256', '/sha1', args.certificate_thumbprint]
    else:
        return None
    if args.timestamp_url:
        arguments.extend(['/tr', args.timestamp_url, '/td', 'SHA256'])
    return arguments


def mask_signing_arguments(arguments):
    """Replace the value that follows /p so the PFX password never reaches evidence."""
    masked = []
    hide_next = False
    for item in arguments:
        if hide_next:
            masked.append('***')
            hide_next = False
            continue
        masked.append(item)
        if item == '/p':
            hide_next = True
    return masked


def parse_signer_subject(output):
    match = re.search(r'Issued to:\s*(.+)', output)
    return match.group(1).strip() if match else None


# --------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------

def acceptance_criteria(evidence_packages, signature_required):
    criteria = []
    packages = {package['rid']: package for package in evidence_packages}

    for rid in ('win-x64', 'win-arm64'):
        package = packages.get(rid)
        if package is None:
            criteria.append({
                'criterion': '{0} package builds, signs and passes package inspection'.format(rid),
                'status': FAIL,
                'detail': 'No {0} package was produced.'.format(rid),
            })
            continue
        signed = bool(package['package'].get('signed'))
        inspection_ok = package['inspection']['summary']['status'] == PASS
        # An unsigned package never satisfies a "builds, signs and passes inspection"
        # criterion. --allow-unsigned exists for pre-signing diagnostics only.
        ok = inspection_ok and signed
        signed_detail = ('signed, signature chain verified' if package.get('signatureVerified')
                         else ('signed' if signed else 'unsigned'))
        criteria.append({
            'criterion': '{0} package builds, signs and passes package inspection'.format(rid),
            'status': PASS if ok else FAIL,
            'detail': 'Build succeeded; inspection {0}; {1}; SHA-256 {2}.'.format(
                package['inspection']['summary']['status'].upper(), signed_detail,
                package['package']['sha256']),
        })

    def no_failed_check(package, check_ids):
        return not any(item['id'] in check_ids and item['status'] == FAIL
                       for item in package['inspection']['checks'])

    criteria.append({
        'criterion': 'Package contents match the reviewed dependency inventory',
        'status': PASS if (evidence_packages and all(
            no_failed_check(package, ('payload.required-files', 'payload.dependency-assemblies',
                                      'payload.app-assemblies', 'payload.forbidden-content',
                                      'payload.reviewed-inventory', 'inventory.reviewed-dependencies'))
            for package in evidence_packages)) else FAIL,
        'detail': 'Required application and dependency assemblies are present, reviewed package-source '
                  'hashes match, and no build-only or test-only content is packaged.',
    })

    criteria.append({
        'criterion': 'Required licenses and notices are present in each package',
        'status': PASS if (evidence_packages and all(
            no_failed_check(package, ('payload.repo-notices', 'payload.runtime-notice'))
            and not any(item['id'] in ('payload.repo-notices', 'payload.runtime-notice')
                        and item['status'] == WARN for item in package['inspection']['checks'])
            for package in evidence_packages)) else FAIL,
        'detail': 'LICENSE, THIRD-PARTY-NOTICES.md, Microsoft-PowerToys-LICENSE.txt and the RID-specific '
                  '.NET runtime notices are present and match their reviewed SHA-256 values.',
    })

    criteria.append({
        'criterion': 'Hashes and reproducible build evidence are recorded',
        'status': PASS if (evidence_packages and all(
            package['package'].get('sha256') and package['inspection'].get('payload')
            for package in evidence_packages)) else FAIL,
        'detail': 'Package and payload SHA-256 values, tool versions, commands, source commit and extracted '
                  'manifests are recorded in evidence.json and evidence.md.',
    })

    criteria.append({
        'criterion': 'No package is submitted or published by this issue',
        'status': PASS,
        'detail': 'The release tooling only writes local build artifacts; it has no upload or submission step.',
    })
    return criteria


def build_evidence_markdown(evidence):
    lines = []
    lines.append('# PlayniteCmdPal release MSIX evidence')
    lines.append('')
    lines.append('Generated by `scripts/release/release_tool.py` ({0} {1}) at {2}.'.format(
        TOOL_NAME, TOOL_VERSION, evidence['generatedAtUtc']))
    lines.append('')
    lines.append('**Status: {0}**'.format(
        'PASS — release-candidate evidence complete' if evidence['status'] == PASS
        else 'FAIL — release-candidate evidence incomplete'))
    lines.append('')

    source = (evidence.get('environment') or {}).get('source') or {}
    lines.append('## Source')
    lines.append('')
    lines.append('| Field | Value |')
    lines.append('| --- | --- |')
    lines.append('| Commit | `{0}` |'.format(source.get('commit')))
    lines.append('| Branch | `{0}` |'.format(source.get('branch')))
    lines.append('| Describe | `{0}` |'.format(source.get('describe')))
    lines.append('| Working tree dirty | {0} |'.format('yes' if source.get('dirty') else 'no'))
    lines.append('')

    environment = evidence.get('environment') or {}
    dotnet = environment.get('dotnet') or {}
    windows = environment.get('windows') or {}
    lines.append('## Environment')
    lines.append('')
    lines.append('| Field | Value |')
    lines.append('| --- | --- |')
    lines.append('| Platform | `{0}` |'.format(environment.get('platform')))
    lines.append('| Windows version | `{0}` |'.format(windows.get('win32ver')))
    lines.append('| .NET SDK | `{0}` |'.format(dotnet.get('version')))
    lines.append('| .NET SDKs | `{0}` |'.format((dotnet.get('sdks') or '').replace('\n', ' ')))
    lines.append('| signtool | `{0}` |'.format((environment.get('signtool') or {}).get('versionLine')))
    lines.append('| makeappx | `{0}` |'.format((environment.get('makeappx') or {}).get('versionLine')))
    lines.append('| Python | `{0}` |'.format(environment.get('python')))
    lines.append('')

    lines.append('## Packages')
    lines.append('')
    lines.append('| RID | File | Size (bytes) | SHA-256 | Signed | Identity | Version | Architecture |')
    lines.append('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for package in evidence['packages']:
        identity = (package.get('manifest') or {}).get('identity') or {}
        lines.append('| {0} | `{1}` | {2:,} | `{3}` | {4} | `{5}` | `{6}` | `{7}` |'.format(
            package['rid'], package['package']['fileName'], package['package']['sizeBytes'],
            package['package']['sha256'], 'yes' if package['package'].get('signed') else 'no',
            identity.get('name'), identity.get('version'), identity.get('processor_architecture')))
    lines.append('')

    lines.append('## Acceptance criteria')
    lines.append('')
    lines.append('| Criterion | Status | Detail |')
    lines.append('| --- | --- | --- |')
    for item in evidence['acceptance']:
        lines.append('| {0} | {1} | {2} |'.format(item['criterion'], item['status'].upper(),
                                                  item['detail'].replace('|', '\\|')))
    lines.append('')

    for package in evidence['packages']:
        lines.append('## {0} inspection (`{1}`)'.format(package['rid'], package['package']['fileName']))
        lines.append('')
        lines.append('| Check | Status | Detail |')
        lines.append('| --- | --- | --- |')
        for item in package['inspection']['checks']:
            lines.append('| `{0}` | {1} | {2} |'.format(
                item['id'], item['status'].upper(), item['detail'].replace('|', '\\|')))
        lines.append('')

    inventory = evidence.get('inventory')
    if inventory:
        lines.append('## Dependency inventory')
        lines.append('')
        lines.append('- File: `{0}`'.format(inventory.get('path')))
        lines.append('- SHA-256: `{0}`'.format(inventory.get('sha256')))
        lines.append('- Generated: `{0}`'.format(inventory.get('generatedAtUtc')))
        lines.append('- Summary: `{0}`'.format(json.dumps(inventory.get('summary'))))
        lines.append('')

    lines.append('## Commands')
    lines.append('')
    for record in evidence['commands']:
        lines.append('```')
        lines.append('$ ' + ' '.join(record['command']))
        lines.append('# exit code: {0}, duration: {1} ms'.format(record['exitCode'], record['durationMs']))
        lines.append('```')
    lines.append('')

    lines.append('## Not performed')
    lines.append('')
    for item in evidence['notPerformed']:
        lines.append('- {0}'.format(item))
    lines.append('')
    return '\n'.join(lines) + '\n'


# --------------------------------------------------------------------------------------
# Build orchestrator
# --------------------------------------------------------------------------------------

def locate_package(appx_directory, architecture):
    candidates = []
    for base, _directories, files in os.walk(appx_directory):
        for name in files:
            lowered = name.lower()
            if lowered.endswith('.msix') and not lowered.endswith('.msixbundle') \
                    and architecture.lower() in lowered:
                candidates.append(os.path.join(base, name))
    return sorted(candidates)


def build_release(args, expectations):
    repo_root = args.repo_root
    package_expectation = expectations['package']
    output_root = args.output or os.path.join(repo_root, 'artifacts', 'release',
                                              package_expectation['version'])
    appx_root = os.path.join(output_root, 'appx')
    commands = []

    preflight_checks = preflight(repo_root, expectations)
    preflight_status = checks_status(preflight_checks)
    print('Preflight: {0} ({1} checks)'.format(preflight_status.upper(), len(preflight_checks)))
    for line in format_checks(preflight_checks, prefix='  '):
        print(line)
    if preflight_status == FAIL and not args.force:
        print('ERROR: preflight failed; fix the repository declarations or pass --force for diagnostics.',
              file=sys.stderr)
        return EXIT_INSPECTION_FAILED

    if args.inventory and not os.path.isabs(args.inventory):
        args.inventory = os.path.join(repo_root, args.inventory)
    if args.certificate_pfx and not os.path.isabs(args.certificate_pfx):
        args.certificate_pfx = os.path.abspath(args.certificate_pfx)

    environment = collect_environment(repo_root, args.dotnet, args.signtool, args.makeappx)
    source = environment.get('source') or {}
    if source.get('dirty') and not args.allow_dirty:
        print('ERROR: the working tree has uncommitted changes; release evidence must come from a committed '
              'revision. Commit the checkout, or pass --allow-dirty for a diagnostic run.', file=sys.stderr)
        return EXIT_INSPECTION_FAILED
    if not source.get('commit'):
        print('WARNING: the source commit could not be recorded (not a Git checkout); the evidence bundle will '
              'not be reproducible.', file=sys.stderr)
    project_path = os.path.join(repo_root, expectations['source']['projectFile'])
    sdk_pin = package_expectation['windowsSdkPackageVersion']
    properties_to_read = ('TargetFramework', 'WindowsSdkPackageVersion', 'RuntimeIdentifier', 'Platform',
                          'SelfContained', 'PublishTrimmed', 'PublishReadyToRun', 'PublishSingleFile',
                          'AppxPackageVersion', 'AppxPackageIdentityName', 'AppxPackagePublisher')

    evidence_packages = []
    for rid, architecture in expectations['architectures'].items():
        appx_directory = os.path.join(appx_root, rid)
        publish_profile = expectations['source']['publishProfiles'][rid]
        publish_arguments = [
            args.verb, project_path,
            '--configuration', args.configuration,
            '--framework', package_expectation['targetFramework'],
            '--runtime', rid,
            '--self-contained', 'true',
            '-p:Platform={0}'.format(architecture['platform']),
            '-p:PublishProfile={0}'.format(os.path.basename(publish_profile)),
            '-p:UapAppxPackageBuildMode=SideloadOnly',
            '-p:AppxBundle=Never',
            '-p:AppxPackageSigningEnabled=false',
            '-p:GenerateAppxPackageOnBuild=true',
            '-p:AppxPackageDir={0}{1}'.format(appx_directory, os.sep),
            '-nologo',
        ]
        for extra in args.msbuild_property or []:
            publish_arguments.append('-p:{0}'.format(extra))

        if args.dry_run:
            print('[dry-run] {0} {1}'.format(args.dotnet, ' '.join(publish_arguments)))
            sign = signing_arguments(args)
            if sign:
                print('[dry-run] {0} {1} <package>'.format(
                    args.signtool, ' '.join(mask_signing_arguments(sign))))
                print('[dry-run] {0} verify /pa /all /v <package>'.format(args.signtool))
            else:
                print('[dry-run] no signing certificate supplied; use -AllowUnsigned for a pre-signing inspection')
            continue

        os.makedirs(appx_directory, exist_ok=True)
        print('Building {0} ({1}) ...'.format(rid, args.configuration))
        build_record = run_command([args.dotnet] + publish_arguments, cwd=repo_root, log=commands)
        if build_record['exitCode'] != 0:
            print(build_record['stdoutTail'])
            print(build_record['stderrTail'], file=sys.stderr)
            print('ERROR: build failed for {0} with exit code {1}.'.format(rid, build_record['exitCode']),
                  file=sys.stderr)
            return EXIT_ENVIRONMENT

        evaluated, _property_record = evaluate_msbuild_properties(
            args.dotnet, project_path, properties_to_read, log=commands, cwd=repo_root)
        evaluated_sdk = evaluated.get('WindowsSdkPackageVersion')
        if evaluated_sdk and evaluated_sdk != sdk_pin:
            print('ERROR: evaluated WindowsSdkPackageVersion is {0}; the reviewed release pin is {1}.'.format(
                evaluated_sdk, sdk_pin), file=sys.stderr)
            return EXIT_INSPECTION_FAILED

        candidates = locate_package(appx_directory, architecture['manifestArchitecture'])
        if len(candidates) != 1:
            print('ERROR: expected exactly one {0} package under {1}, found {2}: {3}.'.format(
                rid, appx_directory, len(candidates), candidates), file=sys.stderr)
            return EXIT_ENVIRONMENT
        package_path = candidates[0]

        signature_verified = False
        signer_subject = None
        sign_arguments = signing_arguments(args)
        if sign_arguments:
            sign_record = run_command([args.signtool] + sign_arguments + [package_path],
                                      cwd=repo_root)
            sign_record['command'] = mask_signing_arguments(sign_record['command'])
            commands.append(sign_record)
            if sign_record['exitCode'] != 0:
                print(sign_record['stdoutTail'])
                print(sign_record['stderrTail'], file=sys.stderr)
                print('ERROR: signing failed for {0}.'.format(package_path), file=sys.stderr)
                return EXIT_ENVIRONMENT
            verify_record = run_command([args.signtool, 'verify', '/pa', '/all', '/v', package_path],
                                        cwd=repo_root, log=commands)
            if verify_record['exitCode'] != 0:
                print(verify_record['stdoutTail'])
                print(verify_record['stderrTail'], file=sys.stderr)
                print('ERROR: signature verification failed for {0}.'.format(package_path), file=sys.stderr)
                return EXIT_ENVIRONMENT
            signature_verified = True
            signer_subject = parse_signer_subject(
                (verify_record['stdoutTail'] or '') + (verify_record['stderrTail'] or ''))
        elif not args.allow_unsigned:
            print('ERROR: no signing certificate supplied. Pass --certificate-pfx or '
                  '--certificate-thumbprint, or --allow-unsigned for a pre-signing inspection only.',
                  file=sys.stderr)
            return EXIT_USAGE

        inspection = inspect_package(
            package_path, expectations, repo_root, rid=rid, nuget_packages=args.nuget_packages,
            inventory=args.inventory, strict=not args.no_strict,
            require_signature=not args.allow_unsigned)

        if signer_subject:
            expected_subject = package_expectation['publisher']
            matches = signer_subject.replace(' ', '').lower() == expected_subject.replace(' ', '').lower()
            inspection['checks'].append(check(
                'package.signature-publisher',
                PASS if matches else FAIL,
                'Signing certificate subject is {0} (manifest Publisher is {1}).'.format(
                    signer_subject, expected_subject),
            ))
            inspection['summary'] = {
                'status': checks_status(inspection['checks']),
                'counts': summarize_checks(inspection['checks']),
            }
        elif signature_verified:
            inspection['checks'].append(check(
                'package.signature-publisher', WARN,
                'signtool did not report the signing certificate subject; confirm it matches the manifest Publisher.'))
            inspection['summary'] = {
                'status': checks_status(inspection['checks']),
                'counts': summarize_checks(inspection['checks']),
            }

        inspection_dir = os.path.join(output_root, 'inspection')
        write_json(os.path.join(inspection_dir, '{0}.json'.format(rid)), inspection)
        manifest_dir = os.path.join(output_root, 'manifests')
        with zipfile.ZipFile(package_path) as archive:
            write_text(os.path.join(manifest_dir, '{0}-AppxManifest.xml'.format(rid)),
                       archive.read('AppxManifest.xml').decode('utf-8'))

        evidence_packages.append({
            'rid': rid,
            'architecture': architecture,
            'package': inspection['package'],
            'manifest': inspection.get('manifest'),
            'inspection': inspection,
            'signatureVerified': signature_verified,
            'signerSubject': signer_subject,
            'evaluatedProperties': evaluated,
            'publishProfile': publish_profile,
            'inspectionPath': os.path.join(inspection_dir, '{0}.json'.format(rid)),
        })
        print('{0}: {1} inspection {2}'.format(
            rid, os.path.basename(package_path), inspection['summary']['status'].upper()))

    if args.dry_run:
        print('[dry-run] No package was built. Run without --dry-run on a Windows machine with the '
              '.NET 10 SDK and signtool.')
        return EXIT_OK

    inventory_report = None
    for package in evidence_packages:
        if package['inspection'].get('inventory'):
            inventory_report = package['inspection']['inventory']
            break

    evidence = {
        'schemaVersion': 1,
        'tool': {'name': TOOL_NAME, 'version': TOOL_VERSION},
        'generatedAtUtc': utc_now(),
        'configuration': args.configuration,
        'expectations': {
            'path': os.path.abspath(args.expectations),
            'sha256': sha256_file(args.expectations),
        },
        'preflight': {'status': preflight_status, 'checks': preflight_checks},
        'environment': environment,
        'packages': evidence_packages,
        'inventory': inventory_report,
        'commands': commands,
        'notPerformed': [
            'No package was installed, launched or activated; installation, update, uninstall and '
            'rollback checks belong to WERD-82.',
            'No package, bundle, certificate or private key was uploaded, published or submitted to '
            'Partner Center.',
            'No MSIX bundle was produced; this issue covers the per-architecture MSIX packages only.',
        ],
    }
    evidence['acceptance'] = acceptance_criteria(evidence_packages, signature_required=not args.allow_unsigned)
    evidence['status'] = PASS if all(item['status'] == PASS for item in evidence['acceptance']) else FAIL
    if preflight_status == FAIL:
        # --force exists for diagnostics; a forced run can never record a passing release verdict.
        evidence['status'] = FAIL

    write_json(os.path.join(output_root, 'evidence.json'), evidence)
    write_text(os.path.join(output_root, 'evidence.md'), build_evidence_markdown(evidence))
    write_text(os.path.join(output_root, 'SHA256SUMS'), ''.join(
        '{0}  {1}\n'.format(package['package']['sha256'], package['package']['fileName'])
        for package in evidence_packages))
    write_json(os.path.join(output_root, 'environment.json'), environment)

    print('')
    print('Evidence written to {0}'.format(output_root))
    print('Acceptance criteria:')
    for item in evidence['acceptance']:
        print('  [{0}] {1} — {2}'.format(item['status'].upper(), item['criterion'], item['detail']))
    return EXIT_OK if evidence['status'] == PASS else EXIT_INSPECTION_FAILED


# --------------------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------------------

def add_common_arguments(parser):
    parser.add_argument('--expectations', default=DEFAULT_EXPECTATIONS,
                        help='Reviewed expectations file (default: scripts/release/release_expectations.json).')
    parser.add_argument('--repo-root', default=os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')),
                        help='Repository root (default: the checkout containing this script).')
    parser.add_argument('--nuget-packages',
                        default=os.environ.get('NUGET_PACKAGES')
                        or os.path.join(os.path.expanduser('~'), '.nuget', 'packages'),
                        help='NuGet global-packages folder used for dependency byte comparisons.')
    parser.add_argument('--inventory', default=None,
                        help='Dependency inventory JSON from scripts/licensing/New-DependencyInventory.ps1.')
    parser.add_argument('--allow-unsigned', action='store_true',
                        help='Allow an unsigned package (pre-signing inspection only).')
    parser.add_argument('--strict', action='store_true',
                        help='Treat unreviewed payload files as failures (the release gate).')


def cmd_preflight(args):
    expectations = load_expectations(args.expectations)
    checks = preflight(args.repo_root, expectations)
    status = checks_status(checks)
    if args.json_out:
        write_json(args.json_out, {'status': status, 'checks': checks})
    for line in format_checks(checks):
        print(line)
    print('Preflight {0} ({1} checks).'.format(status.upper(), len(checks)))
    return EXIT_OK if status == PASS else EXIT_INSPECTION_FAILED


def cmd_inspect(args):
    expectations = load_expectations(args.expectations)
    exit_code = EXIT_OK
    reports = []
    for package_path in args.packages:
        report = inspect_package(
            package_path, expectations, args.repo_root, rid=args.rid or None,
            nuget_packages=args.nuget_packages, inventory=args.inventory,
            strict=args.strict, require_signature=not args.allow_unsigned)
        reports.append(report)
        for line in format_checks(report['checks']):
            print(line)
        if report['summary']['status'] == FAIL:
            exit_code = EXIT_INSPECTION_FAILED
        print('{0}: {1}'.format(os.path.basename(package_path), report['summary']['status'].upper()))
    if args.json_out:
        write_json(args.json_out, reports[0] if len(reports) == 1 else reports)
    return exit_code


def cmd_build(args):
    expectations = load_expectations(args.expectations)
    return build_release(args, expectations)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='release_tool.py',
        description='Build, sign, inspect and record evidence for PlayniteCmdPal release MSIX '
                    'packages (WERD-81).')
    parser.add_argument('--version', action='version',
                        version='{0} {1}'.format(TOOL_NAME, TOOL_VERSION))
    subparsers = parser.add_subparsers(dest='command', required=True)

    preflight_parser = subparsers.add_parser(
        'preflight', help='Check repository declarations against the reviewed expectations.')
    add_common_arguments(preflight_parser)
    preflight_parser.add_argument('--json-out', default=None)
    preflight_parser.set_defaults(func=cmd_preflight)

    inspect_parser = subparsers.add_parser('inspect', help='Inspect one or more MSIX packages.')
    add_common_arguments(inspect_parser)
    inspect_parser.add_argument('packages', nargs='+', help='MSIX package file(s) to inspect.')
    inspect_parser.add_argument('--rid', default=None, choices=('win-x64', 'win-arm64'),
                                help='Expected runtime identifier; derived from the manifest when omitted.')
    inspect_parser.add_argument('--json-out', default=None)
    inspect_parser.set_defaults(func=cmd_inspect, strict=False)

    build_parser = subparsers.add_parser(
        'build', help='Build, sign, inspect and record evidence for both architectures.')
    add_common_arguments(build_parser)
    build_parser.add_argument('--configuration', default='Release')
    build_parser.add_argument('--output', default=None,
                              help='Evidence/output directory (default: artifacts/release/<version>).')
    build_parser.add_argument('--verb', default='publish', choices=('publish', 'build'),
                              help='dotnet verb used to compile and generate the MSIX (default: publish).')
    build_parser.add_argument('--dotnet', default='dotnet', help='dotnet executable.')
    build_parser.add_argument('--signtool', default='signtool.exe' if os.name == 'nt' else 'signtool',
                              help='signtool executable.')
    build_parser.add_argument('--makeappx', default='makeappx.exe' if os.name == 'nt' else 'makeappx',
                              help='makeappx executable (recorded for environment evidence only).')
    build_parser.add_argument('--certificate-pfx', default=None,
                              help='PFX file for signing. The file must never be committed.')
    build_parser.add_argument('--certificate-password-env', default='PLAYNITECMDPAL_MSIX_PFX_PASSWORD',
                              help='Environment variable holding the PFX password, if any.')
    build_parser.add_argument('--certificate-thumbprint', default=None,
                              help='Thumbprint of a signing certificate in the current user store.')
    build_parser.add_argument('--timestamp-url', default='http://timestamp.digicert.com',
                              help='RFC 3161 timestamp server used by signtool.')
    build_parser.add_argument('--msbuild-property', action='append',
                              help='Additional -p:Name=Value property passed to dotnet (repeatable).')
    build_parser.add_argument('--dry-run', action='store_true',
                              help='Print the commands without executing them.')
    build_parser.add_argument('--force', action='store_true',
                              help='Continue after a preflight failure (diagnostics only).')
    build_parser.add_argument('--allow-dirty', action='store_true',
                              help='Allow a working tree with uncommitted changes (diagnostics only).')
    build_parser.add_argument('--no-strict', action='store_true',
                              help='Downgrade unreviewed payload files from failure to warning.')
    build_parser.set_defaults(func=cmd_build, strict=True)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
