# Licensing and release readiness

PlayniteCmdPal-authored material is licensed under the MIT License; see the root [LICENSE](../LICENSE). This grant applies to project-authored material, not automatically to third-party code, template files, trademarks, artwork, SDKs or dependencies. Preserve all applicable third-party notices and comply with each component's terms. This inventory is not a legal opinion.

## Selected project license

The maintainer selected **MIT** for PlayniteCmdPal-authored material. The license permits use, modification and redistribution, including proprietary use, provided the copyright and license notices are retained. It does not include an express patent grant. Contributions submitted to this repository are intended to be offered under the same MIT terms; contributors must ensure they have the right to submit their contributions and must preserve third-party notices and restrictions.

The project license does not relicense Microsoft PowerToys template material or any other third-party component. A future companion Playnite plugin and its dependencies must be reviewed for their own licensing and distribution requirements.

## Inventory and unresolved checks

- Four generated C# files in `testExtension/` carry Microsoft copyright and MIT notices. Their original root-license references pointed to a nonexistent file; the Microsoft PowerToys MIT text is retained separately at [`third-party/Microsoft-PowerToys-LICENSE.txt`](../third-party/Microsoft-PowerToys-LICENSE.txt). Keep the file headers and include the notice when distributing covered material. The project MIT license does not replace this notice.
- The seven checked-in `testExtension/Assets/` PNGs have identical Git blob hashes to the [PowerToys extension template assets at commit 24d81fc](https://github.com/microsoft/PowerToys/tree/24d81fc687c88a230f40ee9a907823d14afa4155/src/modules/cmdpal/ExtensionTemplate/TemplateCmdPalExtension/TemplateCmdPalExtension/Assets). They are template placeholders, not verified release branding. The [PowerToys MIT license](https://github.com/microsoft/PowerToys/blob/24d81fc687c88a230f40ee9a907823d14afa4155/LICENSE) does not itself grant trademark rights. Confirm asset and branding permissions or replace them with appropriately licensed original artwork before release; check any new assets individually.
- `Directory.Packages.props` lists centrally managed versions, not necessarily the resolved dependency graph. The extension directly references `Microsoft.CommandPalette.Extensions`, `Microsoft.Windows.CsWinRT`, `Shmuelie.WinRTServer` and `Microsoft.Windows.SDK.BuildTools.MSIX`; test projects reference `Microsoft.NET.Test.Sdk`, `xunit` and `xunit.runner.visualstudio`. The Windows SDK and transitive/runtime dependencies may add more. Package license texts, redistribution terms, notices and binary inclusion have **not** been verified: nuget.org was not accessible in the earlier review environment and no resolved graph was available. Before distributing, restore on the supported Windows setup, inventory exact direct and transitive versions and published contents, inspect each package's license/terms (including non-SPDX and SDK terms), and bundle required notices. Test/build-only dependencies still need review for their actual use but are not automatically shipped.
- [Playnite](https://github.com/JosefNemec/Playnite/blob/master/LICENSE.md) declares MIT for its repository; this does not establish permission to use Playnite trademarks or artwork, or settle the terms of a future plugin and all its dependencies. No companion plugin is currently checked in. Review the exact SDK, plugin, assets and distribution once selected.
- `testExtension/Package.appxmanifest` still has template identity, Microsoft publisher, display names and version `0.0.1.0`. These are not verified release metadata. Replace with the maintainer's actual package identity, publisher/signing identity and branding before distribution; do not imply Microsoft publishes the extension.

## Before the first public release

1. Complete the dependency, asset, attribution and contribution-rights review above. Obtain permission where needed; do not ship unverified third-party artwork.
2. Decide and document a versioning policy, including pre-release and breaking-change handling. Choose whether a checked-in changelog is warranted; do not treat the template's `0.0.1.0` as a published version.
3. Decide where release notes live and their format (at minimum: version/date, changes, known issues, compatibility and upgrade instructions). Record the decision before publishing.
4. Set and validate package identity, signing/publisher information, display names and consistent version metadata. Confirm artifact contents and required third-party notices for each distribution channel.
5. Complete the Windows build, deployment, integration and security checks tracked by the project; do not describe the template as a verified release.
