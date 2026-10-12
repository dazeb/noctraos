# assets/branding

Unused. Artwork lives next to what uses it:

- `assets/icons/` — the logo (`noctraos-logo.svg`), the "N" mark, agent and category glyphs
- `assets/wallpapers/` — the six 4K wallpapers (both flavours)
- `assets/boot/` — GRUB, Plymouth and isolinux art; `assets/boot/calamares/` is the kubuntu installer's logo, welcome
  picture and slideshow
- `assets/plasma/` — kubuntu flavour: the SDDM login background and logo, and the Global Theme package
  `look-and-feel/dev.noctraos.desktop` (installed by `configs/plasma/install-look.sh`)
- `assets/social/`, `assets/promo/` — website and launch images (not shipped in update bundles)

The kubuntu artwork is rendered by `scripts/render-kubuntu-branding.py` (headless Chrome, the fonts in `assets/social/fonts`);
rerun it after a change to the slides, the palette or the logo and commit the outputs.
