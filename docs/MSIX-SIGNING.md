# MSIX publisher identity and signing

**Status (2026-11-01): blocked pending maintainer-supplied distribution identity and publisher-controlled signing certificate.** This document records the safe procedure and the evidence that must be captured. It does not assert that the provisional identity is valid.

## 1. Distribution channel and identity source

The release plan currently prefers Microsoft Store and treats WinGet as an unselected alternative. This is an investigation direction, not a confirmed distribution decision. The maintainer must confirm the channel before identity or signing values are finalized.

For a Microsoft Store release:

1. The maintainer reserves/opens the product in Partner Center under the intended publisher account.
2. Copy the exact package identity **Name** and **Publisher** values from the product's package identity details. Do not derive either value from the repository name, display name, a self-signed certificate, or an existing development package.
3. Record the Partner Center product identifier and the date/account context needed to reproduce the lookup. Do not record account credentials or private account data.
4. Update `PlayniteCmdPal/Package.appxmanifest` (and any project packaging properties that override it) with the exact identity values. Preserve the intended package identity across upgrades.
5. If a different distribution channel is approved, document its authoritative package-ID and publisher source before changing the manifest.

Until those steps are complete, `Name="PlayniteCmdPal"` and `Publisher="CN=PlayniteCmdPal"` remain provisional. Do not submit a package or Gallery listing based on them.

## 2. Publisher certificate requirements

The signing certificate must be controlled by the selected publisher and its Subject distinguished name must match the manifest `Identity Publisher` value **exactly**, including the complete subject string and relevant distinguished-name formatting.

Before using a certificate, record and independently verify:

- Exact certificate Subject (must equal the manifest Publisher byte-for-byte as represented by the manifest value).
- SHA-1 certificate thumbprint (identifier only; not a secret).
- Issuer, validity period, code-signing EKU, and certificate-chain trust status.
- Whether the private key is present and usable by the authorized signing identity.
- Certificate provenance/ownership and the publisher account or organization that controls it.
- Whether the chosen channel requires a particular certificate profile, timestamping policy, or signing service.

A certificate subject match alone does not prove publisher control or trust. A self-signed development certificate is not evidence of a production publisher identity.

### Secret handling

- Never commit a PFX/P12, PEM private key, password, signing token, or certificate-store export containing private key material.
- Never attach private keys or passwords to Linear, GitHub issues, pull requests, or repository artifacts.
- Prefer a managed signing service or an access-controlled Windows certificate store/HSM. Restrict signing permissions to the release workflow and authorized maintainers.
- If CI signing is approved, store credentials only in the CI secret store or use a managed identity/OIDC-backed signing service where supported. Do not print secrets or command lines containing passwords in logs.
- It is acceptable to publish the public certificate, subject, thumbprint, issuer, validity dates, and verification output when appropriate; never publish the private key.

## 3. Signing and verification procedure

Use the signing method required by the confirmed distribution channel. Do not assume that the local sideload-signing process is identical to the Store submission/signing process. Confirm whether packages are to be signed locally, signed by a managed publisher service, or submitted for Store signing before running a release signing job.

For a locally signed candidate, use the approved publisher-controlled certificate from the authorized certificate store or signing service. Configure SHA-256 file and timestamp digests. Use an RFC 3161 timestamp authority approved for the release, and retain its URL and successful timestamp verification output as evidence. Do not hard-code an unapproved timestamp provider.

After signing each architecture candidate:

1. Run SignTool package signature verification (for example, `signtool verify /pa /v <package.msix>`) on the signed MSIX.
2. Confirm the signer Subject exactly matches the manifest Publisher.
3. Confirm the signer thumbprint matches the recorded certificate.
4. Confirm the certificate chain builds to a trusted root on a clean supported Windows machine.
5. Confirm the signature and timestamp are valid and the timestamp is present when required by the selected channel/certificate policy.
6. Record the command, SignTool/Windows SDK version, exit code, verification output, package SHA-256, signer subject/thumbprint, and timestamp authority. Redact local paths or account details if they reveal sensitive information.

A successful signature check on one architecture does not establish that the other package was signed or verified.

## 4. Version mapping

The current manifest version is `0.0.3.0`. For a stable SemVer release `MAJOR.MINOR.PATCH`, use the corresponding four-part MSIX version `MAJOR.MINOR.PATCH.0` (for example, `0.0.3` → `0.0.3.0`). Keep the manifest, evaluated package version, release tag, and release metadata synchronized.

Before a release candidate is built, record the exact SemVer tag and evaluated MSIX version for both architecture builds. Do not invent a fourth component for a prerelease or submit a SemVer prerelease to a channel that does not support that mapping; define and document a separate monotonic prerelease policy before producing such packages.

## 5. Validation record

The following values are intentionally unresolved until obtained from the authoritative provider and publisher-controlled certificate. Do not fill them with development-certificate values.

| Evidence | Required value | Current status |
| --- | --- | --- |
| Distribution channel | Maintainer-confirmed channel | Microsoft Store preferred in release plan; not confirmed |
| Provider identity source | Partner Center product identity (or equivalent authoritative source) | Not supplied |
| Package identity Name | Exact provider value | Provisional: `PlayniteCmdPal` |
| Manifest Publisher | Exact provider publisher value | Provisional: `CN=PlayniteCmdPal` |
| Certificate Subject | Exact publisher-controlled certificate subject | Not supplied |
| Certificate thumbprint | Public certificate thumbprint | Not supplied |
| Certificate trust | Chain and code-signing suitability verified on clean Windows | Not verified |
| Timestamp policy/provider | Channel-approved policy and RFC 3161 authority, if required | Not confirmed |
| x64 candidate | Signed package hash and successful signature verification | Not built/verified for this issue |
| ARM64 candidate | Signed package hash and successful signature verification | Not built/verified for this issue |
| Version | SemVer tag and evaluated four-part MSIX version | Current manifest only: `0.0.3.0` |

Do not mark this issue complete until the provider identity and certificate are supplied, the manifest/certificate subject equality is demonstrated, and both architecture candidates pass the selected channel's signing and verification process. WERD-81 owns the reproducible package build and inspection evidence and depends on this identity gate.

## 6. Related release gates

- [Release packaging](RELEASE-PACKAGING.md) defines the selected packaging model and overall release checklist.
- [WERD-76](https://linear.app/werdscopez7347/issue/WERD-76/obtain-authoritative-redistribution-clearance-for-windows-sdk) tracks Windows SDK projection redistribution clearance.
- [WERD-77](https://linear.app/werdscopez7347/issue/WERD-77/evaluate-and-migrate-from-the-preview-windows-sdk-targeting-pack) tracks migration from the preview targeting pack and Windows validation.
- [WERD-78](https://linear.app/werdscopez7347/issue/WERD-78/run-the-windows-release-dependency-inventory-and-verify-runtime) tracks the dependency inventory and per-RID runtime notices.
- [WERD-81](https://linear.app/werdscopez7347/issue/WERD-81/build-and-inspect-x64-and-arm64-release-msix-packages) builds and inspects the x64 and ARM64 release packages.
