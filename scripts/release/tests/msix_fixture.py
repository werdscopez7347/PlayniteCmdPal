"""Synthetic MSIX fixtures for the release-tool self-tests.

The fixtures are deliberately small but structurally faithful: an OPC ZIP archive with
AppxManifest.xml, AppxBlockMap.xml, [Content_Types].xml, an optional AppxSignature.p7x,
and a payload shaped like the real self-contained publish output. They let the
inspection logic be exercised without a Windows build.
"""

import os
import zipfile
from pathlib import Path

import release_tool

DEFAULT_CLASS_ID = '5fa90ed5-fcab-47c0-bbc0-e0b72f39aa16'
MANIFEST_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
  xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
  xmlns:uap3="http://schemas.microsoft.com/appx/manifest/uap/windows10/3"
  xmlns:com="http://schemas.microsoft.com/appx/manifest/com/windows10"
  xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
  IgnorableNamespaces="uap uap3 rescap">

  <Identity
    Name="{identity_name}"
    Publisher="{publisher}"
    Version="{version}"
    ProcessorArchitecture="{architecture}" />

  <Properties>
    <DisplayName>{display_name}</DisplayName>
    <PublisherDisplayName>{publisher_display_name}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Universal" MinVersion="{minimum_os}" MaxVersionTested="{minimum_os}" />
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="{minimum_os}" MaxVersionTested="{minimum_os}" />
  </Dependencies>

  <Resources>
    <Resource Language="{language}" />
  </Resources>

  <Applications>
    <Application Id="App" Executable="{executable}" EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements
        DisplayName="{display_name}"
        Description="Playnite Command Palette extension host."
        BackgroundColor="transparent"
        Square150x150Logo="Assets\\Square150x150Logo.png"
        Square44x44Logo="Assets\\Square44x44Logo.png"
        AppListEntry="{app_list_entry}">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png" />
        <uap:SplashScreen Image="Assets\\SplashScreen.png" />
      </uap:VisualElements>
      <Extensions>
        {com_extension}
        <uap3:Extension Category="windows.appExtension">
          <uap3:AppExtension Name="{extension_name}"
            Id="ID"
            PublicFolder="Public"
            DisplayName="Playnite"
            Description="Search and launch games from your Playnite library.">
            <uap3:Properties>
              <CmdPalProvider>
                <Activation>
                  <CreateInstance ClassId="{class_id}" />
                </Activation>
                <SupportedInterfaces>
                  <Commands />
                </SupportedInterfaces>
              </CmdPalProvider>
            </uap3:Properties>
          </uap3:AppExtension>
        </uap3:Extension>
      </Extensions>
    </Application>
  </Applications>

  <Capabilities>
    <Capability Name="internetClient" />
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""

EXE_SERVER_EXTENSION = """<com:Extension Category="windows.comServer">
          <com:ComServer>
            <com:ExeServer Executable="{executable}" Arguments="{arguments}" DisplayName="Playnite">
              <com:Class Id="{class_id}" DisplayName="Playnite" />
            </com:ExeServer>
          </com:ComServer>
        </com:Extension>"""

IN_PROCESS_SERVER_EXTENSION = """<com:Extension Category="windows.comServer">
          <com:ComServer>
            <com:InProcessServer>
              <com:Class Id="{class_id}" DisplayName="Playnite" />
            </com:InProcessServer>
          </com:ComServer>
        </com:Extension>"""

CONTENT_TYPES_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
{defaults}{overrides}
</Types>
"""

BLOCKMAP_TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<BlockMap xmlns="http://schemas.microsoft.com/appx/2010/blockmap" HashMethod="http://www.w3.org/2001/04/xmlenc#sha256">
{files}
</BlockMap>
"""

OMITTED_DEFAULT_EXTENSIONS = ()


def manifest_text(architecture='x64', overrides=None):
    expectations = release_tool.load_expectations(release_tool.DEFAULT_EXPECTATIONS)
    package = expectations['package']
    com = expectations['comServer']
    app_extension = expectations['appExtension']
    values = {
        'identity_name': package['identityName'],
        'publisher': package['publisher'],
        'version': package['version'],
        'architecture': architecture,
        'display_name': package['displayName'],
        'publisher_display_name': package['publisherDisplayName'],
        'minimum_os': package['minimumOsVersion'],
        'language': 'en-US',
        'executable': package['applicationExecutable'],
        'app_list_entry': package['appListEntry'],
        'extension_name': app_extension['name'],
        'class_id': com['classId'],
        'arguments': com['arguments'],
        'com_extension': EXE_SERVER_EXTENSION.format(executable=package['applicationExecutable'],
                                                     arguments=com['arguments'],
                                                     class_id=com['classId']),
    }
    overrides = overrides or {}
    if overrides.get('com_extension') == 'in-process':
        values['com_extension'] = IN_PROCESS_SERVER_EXTENSION.format(class_id=com['classId'])
    values.update({key: value for key, value in overrides.items() if key != 'com_extension'})
    return MANIFEST_TEMPLATE.format(**values)


def default_notice_bytes():
    # Larger than the reviewed minimum (50,000 bytes) so size checks are exercised.
    block = b'PlayniteCmdPal test runtime notice. '
    return (block * ((78041 // len(block)) + 1))[:78041]


def read_repo_file(repo_root, relative):
    return (Path(repo_root) / relative).read_bytes()


def payload_files(repo_root, rid='win-x64', notice_bytes=None):
    notice = notice_bytes if notice_bytes is not None else default_notice_bytes()
    return {
        'PlayniteCmdPal.exe': b'MZ' + b'\x00' * 2048,
        'PlayniteCmdPal.dll': b'app-assembly' + b'\x01' * 2048,
        'PlayniteCmdPal.Core.dll': b'core-assembly' + b'\x02' * 2048,
        'PlayniteCmdPal.Playnite.dll': b'adapter-assembly' + b'\x03' * 2048,
        'PlayniteCmdPal.Snapshot.dll': b'snapshot-assembly' + b'\x04' * 2048,
        'PlayniteCmdPal.deps.json': b'{"runtimeTarget":{}}',
        'PlayniteCmdPal.runtimeconfig.json': b'{"runtimeOptions":{}}',
        'Microsoft.CommandPalette.Extensions.winmd': b'winmd' * 512,
        'Microsoft.Windows.SDK.NET.dll': b'sdk-projection' * 1024,
        'WinRT.Runtime.dll': b'winrt-runtime' * 1024,
        'Shmuelie.WinRTServer.dll': b'winrt-server' * 1024,
        'LICENSE': read_repo_file(repo_root, 'LICENSE'),
        'THIRD-PARTY-NOTICES.md': read_repo_file(repo_root, 'third-party/THIRD-PARTY-NOTICES.md'),
        'Microsoft-PowerToys-LICENSE.txt': read_repo_file(repo_root, 'third-party/Microsoft-PowerToys-LICENSE.txt'),
        'dotnet-runtime-THIRD-PARTY-NOTICES.txt': notice,
        'coreclr.dll': b'coreclr' * 128,
        'System.Private.CoreLib.dll': b'corelib' * 128,
        'System.Runtime.dll': b'system-runtime' * 128,
        'resources.pri': b'pri-binary',
        'Assets/StoreLogo.png': b'png-store-logo',
        'Assets/Square150x150Logo.scale-200.png': b'png-150',
        'Assets/Square44x44Logo.scale-200.png': b'png-44',
        'Assets/Square44x44Logo.targetsize-24_altform-unplated.png': b'png-44-24',
        'Assets/Wide310x150Logo.scale-200.png': b'png-wide',
        'Assets/SplashScreen.scale-200.png': b'png-splash',
    }


def package_files(repo_root, rid='win-x64', architecture='x64', manifest_overrides=None,
                  notice_bytes=None, payload_overrides=None, drop=()):
    files = payload_files(repo_root, rid=rid, notice_bytes=notice_bytes)
    files.update(payload_overrides or {})
    for name in drop:
        files.pop(name, None)
    files['AppxManifest.xml'] = manifest_text(
        architecture=architecture, overrides=manifest_overrides).encode('utf-8')
    return files


def _content_types(extensions, extensionless=()):
    defaults = []
    for extension in sorted(set(extensions)):
        if extension in OMITTED_DEFAULT_EXTENSIONS:
            continue
        if extension in ('xml', 'p7x'):
            content_type = 'application/vnd.ms-appx.signature' if extension == 'p7x' else 'application/xml'
        elif extension in ('exe', 'dll', 'pri', 'winmd'):
            content_type = 'application/octet-stream'
        elif extension == 'png':
            content_type = 'image/png'
        elif extension == 'json':
            content_type = 'application/json'
        else:
            content_type = 'text/plain'
        defaults.append('  <Default Extension="{0}" ContentType="{1}" />'.format(extension, content_type))
    overrides = ['  <Override PartName="/{0}" ContentType="text/plain" />'.format(name)
                 for name in sorted(extensionless)]
    return CONTENT_TYPES_TEMPLATE.format(defaults='\n'.join(defaults),
                                         overrides=('\n' + '\n'.join(overrides)) if overrides else '')


def write_package(path, files, include_signature=True, blockmap_omit=(), content_types_omit=(),
                  signature_bytes=b'test-signature-block', blockmap_extra=()):
    payload = {name: data for name, data in files.items() if name != 'AppxManifest.xml'}
    extensions = []
    for name in list(payload) + ['AppxManifest.xml']:
        extension = name.rsplit('.', 1)[-1] if '.' in name.rsplit('/', 1)[-1] else ''
        if extension:
            extensions.append(extension)
    extensionless = [name for name in list(payload) + ['AppxManifest.xml']
                     if '.' not in name.rsplit('/', 1)[-1]]
    entries = dict(files)
    entries['[Content_Types].xml'] = _content_types(
        [extension for extension in extensions if extension not in content_types_omit],
        extensionless).encode('utf-8')

    blockmap_names = sorted((set(files) - set(blockmap_omit)) | set(blockmap_extra))
    blockmap_files = ['  <File Name="{0}" Size="{1}" LfhSize="40" />'.format(
        name.replace('/', '\\'), len(files.get(name, b''))) for name in blockmap_names]
    entries['AppxBlockMap.xml'] = BLOCKMAP_TEMPLATE.format(files='\n'.join(blockmap_files)).encode('utf-8')
    if include_signature:
        entries['AppxSignature.p7x'] = signature_bytes

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(entries):
            archive.writestr(name, entries[name])
    return path


def write_nuget_package(root, package_id, version, file_name, data, framework='net8.0'):
    path = Path(root) / package_id.lower() / version / 'lib' / framework / file_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
