# Microsoft Store package identity and MSIX signing

**Status (2026-11-17): Partner Center identity values supplied and applied to the manifest; release-candidate build,
signing and inspection tooling implemented.** Store submission, package validation and certification have not
been completed, and the signed x64/ARM64 release candidates have not been produced yet.

## 1. Distribution decision and authoritative identity

The selected primary distribution channel is **Microsoft Store using an MSIX bundle**. The intended architecture coverage is x64 and ARM64. GitHub Releases and WinGet are additional distribution paths; they do not inherit Microsoft Store signing or SmartScreen treatment. Command Palette Gallery metadata should offer Microsoft Store and WinGet as the installation choices once both sources are live.

The maintainer supplied the following Partner Center product identity values:

| Partner Center field | Value |
| --- | --- |
| Package/Identity/Name | `werdscopez7347.PlayniteforCommandPalette` |
| Package/Identity/Publisher | `CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70` |
| Package/Properties/PublisherDisplayName | `werdscopez7347` |

These exact values are applied to `PlayniteCmdPal/Package.appxmanifest` and to the project properties `AppxPackageIdentityName` and `AppxPackagePublisher` in `PlayniteCmdPal/PlayniteCmdPal.csproj`. The project also sets `AppxPackageVersion` to `0.0.8.0`, matching the manifest. The app's `DisplayName` remains `PlayniteCmdPal`; it is distinct from `PublisherDisplayName`.

Do not replace these identity values with the repository name, a display name, or a development certificate subject. Preserve the package identity across updates. If Partner Center later shows different identity values, stop and reconcile the discrepancy before building or submitting a package.

The Partner Center product ID / Store URL has not been supplied and must not be guessed.

## 2. Store-managed signing

For packages distributed through Microsoft Store, the publisher does not need to purchase, provision, or manage a production code-signing certificate. Submit the unsigned MSIX package/bundle through Partner Center; Microsoft performs certification and signs the Store-distributed package.

Consequences:

- Do not create a publisher-controlled certificate requirement for the Store submission path.
- Do not add a PFX, private key, certificate password, or signing token to this repository, Linear, or release artifacts.
- Do not run a local self-signed certificate workflow as a substitute for Store signing.
- Store signing applies to the Store-distributed package. A copy downloaded directly from GitHub or installed through a WinGet manifest that points to GitHub is a separate distribution path and does not automatically receive Store signing or Store installation reputation.
- If direct-download MSIX distribution is retained, its signing/trust model must be evaluated and documented separately. Do not claim that Store certification covers those files.

Microsoft references:
- [Code-signing options for MSIX](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options)
- [Publish Command Palette extensions in Microsoft Store](https://learn.microsoft.com/en-us/windows/powertoys/command-palette/publish-extension-store)

## 3. Package build and Store submission

Follow Microsoft's current Command Palette Store publishing guide for the exact Partner Center workflow and packaging commands. The release candidate must:

1. Use the Partner Center identity values above. `python scripts/release/release_tool.py preflight` fails when the manifest, project, or reviewed expectations disagree.
2. Include both supported architectures, x64 and ARM64, in the Store submission bundle.
3. Use the same package identity and release version across both architecture builds.
4. Pass the Store packaging and validation checks before upload.
5. Be uploaded to the reserved Partner Center product and pass certification before being described as available in the Store.

Keep the package manifest version, evaluated package version, SemVer release tag, and release metadata synchronized. The current manifest and project version is `0.0.8.0`; SemVer `0.0.8` maps to MSIX `0.0.8.0`. Do not increment the version merely for applying the identity.

Record the following evidence when the actual build/submission is performed:

- Git commit and SemVer tag.
- .NET SDK, Windows SDK / MSIX tooling, and build environment versions.
- x64 and ARM64 package filenames, evaluated package versions, and SHA-256 hashes.
- Store bundle filename and SHA-256 hash.
- Package validation command, exit code, and output.
- Partner Center submission identifier, certification result, and Store product URL when available.

`python scripts/release/release_tool.py build` produces these values as an evidence bundle
(`artifacts/release/<version>/evidence.json` and `evidence.md`): the source commit, Windows/.NET/MSBuild/signtool
versions, both package filenames and SHA-256 hashes, the extracted `AppxManifest.xml`, and every inspection result.
See [Release packaging](RELEASE-PACKAGING.md#10-release-msix-build-and-inspection-werd-81) and
[WERD-81 release evidence](RELEASE-EVIDENCE-WERD-81.md).

Do not commit generated packages or private signing material.

## 4. Local candidate signing vs Store-managed signing

The Store submission itself must be unsigned; Microsoft signs the certified package. A local release candidate
still needs a signature so the identity can be validated with `signtool` before submission. Use a test
certificate whose subject equals the manifest Publisher (`CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70`), keep the
PFX and password outside the repository (for example `C:\secure\`), and let `scripts/release/release_tool.py build` sign
(`signtool sign /fd SHA256`), timestamp and verify (`signtool verify /pa /all /v`) the package. The tool records
the signer subject, compares it with the Publisher, and fails on a mismatch. A self-signed test certificate must
be imported into the current user's root store before `signtool verify /pa` can succeed
(`Import-Certificate -FilePath <file.cer> -CertStoreLocation Cert:\CurrentUser\Root`); import only the public
`.cer`. Repository ignore rules cover
`*.pfx`, `*.p12`, `*.cer` and `*.pvk` so a stray key is never staged, and `build` prints a warning and records
`environment.signing.certificateInsideRepository` when the certificate path is inside the checkout. This is a local engineering
validation, not a production certificate, Store certification, or a trust claim for direct downloads.

## 5. Validation record

| Evidence | Current value / status |
| --- | --- |
| Primary distribution | Microsoft Store via MSIX bundle |
| Additional distribution | GitHub Releases and WinGet; direct-download trust remains separate |
| Gallery install choices | Microsoft Store and WinGet, after each source is live |
| Package identity Name | `werdscopez7347.PlayniteforCommandPalette` |
| Manifest Publisher | `CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70` |
| Publisher display name | `werdscopez7347` |
| Manifest updated | Yes, on the WERD-79 branch |
| Project MSIX identity properties | Set to the same Partner Center name and publisher |
| Project MSIX package version | `0.0.8.0`, matching the manifest |
| Partner Center product ID / Store URL | Not supplied |
| x64 MSIX candidate | Not yet signed or inspected; `dotnet publish` produces `PlayniteCmdPal_0.0.8.0_x64.msix` (`scripts/release/release_tool.py build`) |
| ARM64 MSIX candidate | Not yet built or inspected; pipeline ready |
| MSIX bundle | Not yet built and validated |
| Partner Center certification | Not submitted |
| Store listing availability | Not published |
| Current manifest version | `0.0.8.0` |
| Release SDK pin | `Microsoft.Windows.SDK.NET.Ref 10.0.26100.84` (REDIST-listed; enforced by the release preflight) |
| Evidence bundle | [WERD-81 release evidence](RELEASE-EVIDENCE-WERD-81.md) |

## 6. Signing a package when the PFX password is unknown

The local test certificate is disposable: the release gate checks that the signer subject equals the manifest
Publisher, not that a particular key survives. **Only a certificate whose subject is exactly
`CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70` can sign a release candidate.** Development certificates named
`CN=PlayniteCmdPal` sign fine but fail the identity gate, so they are not an option here.

`--certificate-thumbprint` takes the 40 hexadecimal characters of a SHA-1 thumbprint; the spacing that
`Get-ChildItem` or `certutil` prints is tolerated. A placeholder or a truncated value is rejected before anything
is built.

Two paths, in order of preference:

1. **Use the certificate copy in the user store.** If the certificate used to create the PFX is still installed,
   signing needs no password at all:

   ```powershell
   Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Format-List Subject, Thumbprint, HasPrivateKey
   python scripts/release/release_tool.py build `
       --inventory artifacts/dependency-inventory.json `
       --certificate-thumbprint <thumbprint>
   ```

   The subject must be `CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70` and `HasPrivateKey` must be `True`.

2. **Recreate the test certificate with a known password.** Acceptable because it is a local engineering
   validation, not a distribution identity. Keep the subject identical to the manifest Publisher:

   ```powershell
   $cert = New-SelfSignedCertificate -Type Custom `
       -Subject 'CN=B5EE8A57-B227-4726-A4E9-AF40E9D47E70' `
       -KeyUsage DigitalSignature -FriendlyName 'PlayniteCmdPal test signing' `
       -CertStoreLocation 'Cert:\CurrentUser\My' `
       -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3', '2.5.29.19={text}')
   $password = ConvertTo-SecureString -String '<new password>' -Force -AsPlainText
   Export-PfxCertificate -Cert $cert -FilePath C:\secure\PlayniteCmdPal-Test.pfx -Password $password
   Export-Certificate -Cert $cert -FilePath C:\secure\PlayniteCmdPal-Test.cer
   Import-Certificate -FilePath C:\secure\PlayniteCmdPal-Test.cer -CertStoreLocation Cert:\CurrentUser\Root
   ```

   Then set `PLAYNITECMDPAL_MSIX_PFX_PASSWORD` for the run. Record the new thumbprint in the validation record
   below, and never commit the PFX or the password.

`build` prints both remedies when signtool reports `The specified PFX password is not correct`.

## 7. Release gates and dependencies

This issue establishes the Store identity and documents the Store-managed signing model. It does not complete package production or Store certification.

- [WERD-76](https://linear.app/werdscopez7347/issue/WERD-76/obtain-authoritative-redistribution-clearance-for-windows-sdk) tracks Windows SDK projection redistribution clearance.
- [WERD-77](https://linear.app/werdscopez7347/issue/WERD-77/evaluate-and-migrate-from-the-preview-windows-sdk-targeting-pack) tracks migration from the preview targeting pack and Windows validation.
- [WERD-78](https://linear.app/werdscopez7347/issue/WERD-78/run-the-windows-release-dependency-inventory-and-verify-runtime) tracks dependency inventory and per-RID runtime notices.
- WERD-81 owns the x64/ARM64 package build and inspection evidence; see [WERD-81 release evidence](RELEASE-EVIDENCE-WERD-81.md).
- WERD-83 remains the final release go/no-go gate.

Do not mark WERD-79 complete until the Partner Center identity is confirmed in the product dashboard, the manifest changes are reviewed, and the Store package identity/build prerequisites are validated. Package build and certification remain separate release gates.
