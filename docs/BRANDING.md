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
| Wide tile and splash | `PlayniteCmdPal/Assets/Wide310x150Logo.scale-200.png`, `SplashScreen.scale-200.png` | `icons/png/msix/Wide310x150Logo.scale-200.png` |

The MSIX manifest owns the asset filenames and logical surfaces. Keep the manifest references and checked-in files in sync. The existing package identity, publisher, COM class, and Command Palette extension registration are not branding assets and must not be changed as part of a visual refresh.

## Source of truth and regeneration

- Edit SVGs under `PlayniteCmdPal-Brand-Assets/svg/` as the vector source.
- Regenerate raster, ICO, and preview outputs with `PlayniteCmdPal-Brand-Assets/scripts/generate-assets.py`.
- Keep the Inter OFL and third-party notices in the brand package when redistributing the font files.
- Update this mapping if the manifest's asset declarations change.
