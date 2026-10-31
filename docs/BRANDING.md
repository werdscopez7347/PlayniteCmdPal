# PlayniteCmdPal branding integration

The authoritative brand source package is [PlayniteCmdPal-Brand-Assets](../PlayniteCmdPal-Brand-Assets/README.md). Keep its SVGs, generated raster assets, ICO files, generator, previews, and licensing notes together.

## Runtime mapping

| Product surface | Runtime asset | Source |
|---|---|---|
| Executable icon | `PlayniteCmdPal-Brand-Assets/icons/ico/PlayniteCmdPal.ico` | Multi-resolution application icon |
| MSIX store logo | `PlayniteCmdPal/Assets/StoreLogo.png` | `icons/png/msix/StoreLogo.scale-100.png` |
| MSIX square tile | `PlayniteCmdPal/Assets/Square150x150Logo.scale-200.png` | `icons/png/msix/Square150x150Logo.scale-200.png` |
| MSIX small tile | `PlayniteCmdPal/Assets/Square44x44Logo.scale-200.png` | `icons/png/msix/Square44x44Logo.scale-200.png` |
| Small unplated glyph | `PlayniteCmdPal/Assets/Square44x44Logo.targetsize-24_altform-unplated.png` | `icons/png/msix/Square44x44Logo.targetsize-24_altform-unplated.png` |
| Wide tile | `PlayniteCmdPal/Assets/Wide310x150Logo.scale-200.png` | `icons/png/msix/Wide310x150Logo.scale-200.png` |
| Splash screen | `PlayniteCmdPal/Assets/SplashScreen.scale-200.png` (1240×600) | `icons/png/msix/Wide310x150Logo.scale-400.png` (1240×600) |

The MSIX manifest owns the asset filenames and logical surfaces. Keep the manifest references and checked-in files in sync. The existing package identity, publisher, COM class, and Command Palette extension registration are not branding assets and must not be changed as part of a visual refresh.

## Source of truth and regeneration

- Edit SVGs under `PlayniteCmdPal-Brand-Assets/svg/` as the vector source.
- Regenerate raster, ICO, and preview outputs with `PlayniteCmdPal-Brand-Assets/scripts/generate-assets.py`.
- Keep the Inter OFL and third-party notices in the brand package when redistributing the font files.
- Update this mapping if the manifest's asset declarations change.
- The generated brand README records the integration mapping; `write_readme()` in the generator holds the same wording. Update both together if the mapping changes.

## Package asset selection

The manifest declares a single logical asset per surface (`Assets\StoreLogo.png`, `Assets\Square150x150Logo.png`, …). Windows resolves the scale-qualified file for the current DPI, so only the density variants the project actually ships are listed in `PlayniteCmdPal.csproj`. The checked-in set is scale-200 (plus one `targetsize-24` unplated glyph); the remaining `icons/png/msix/` variants stay in the brand package as the source for higher-density exports. Adding a `scale-100` or `scale-400` file for a surface means adding a matching `Content` item and keeping the dimensions consistent with the logical size (for example `Square150x150Logo` = 150 px at scale 100, 300 px at scale 200, 600 px at scale 400).

Verified dimensions of the checked-in files:

| File | Pixels | Logical size |
|---|---|---|
| `StoreLogo.png` | 50 × 50 | 50 × 50 |
| `Square44x44Logo.scale-200.png` | 88 × 88 | 44 × 44 |
| `Square44x44Logo.targetsize-24_altform-unplated.png` | 24 × 24 | 24 × 24 |
| `Square150x150Logo.scale-200.png` | 300 × 300 | 150 × 150 |
| `Wide310x150Logo.scale-200.png` | 620 × 300 | 310 × 150 |
| `SplashScreen.scale-200.png` | 1240 × 600 | 620 × 300 |
| `LockScreenLogo.scale-200.png` | 48 × 48 | 24 × 24 (retained file, not referenced by the manifest) |

The 1240 × 600 splash image is the wide-lockup density export, deliberately stored in the scale-200 splash slot: the file name and the pixel size do not agree, and that is intentional because the manifest exposes a single `Assets\SplashScreen.png` logical file. Do not "fix" it by downscaling to 620 × 300.

## Known branding-scope limitations

- `AppListEntry="none"` hides the packaged host from the app list. The executable icon set by `<ApplicationIcon>` covers the `.exe` file in Explorer and the window icon; it is not a guarantee about the icon the host process shows in the taskbar, which is chosen by the process itself.
- The ICO carries 16, 24, 32 (small optical variant), 48, 64, 128 (DIB) and 256 (PNG) entries. The 256 entry is the only PNG-compressed image in the file, so tools that reject PNG-in-ICO would lose only jumbo-size rendering.
- The package `PublisherDisplayName` and `DisplayName` remain `PlayniteCmdPal` while the user-visible extension, COM server, class, and command item are named `Playnite`. That split is deliberate and is not a branding defect: the package identity must stay stable for update continuity.
