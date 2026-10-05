#!/usr/bin/env bash
# strip-census.sh — takes Zorin's usage census out of the installer and the installed system.
# Sourced by build-noctraos-iso.sh.
#
#   strip_census <squashfs-root>
#
# Zorin OS counts installs: the zorin-os-census package ships a cron job that posts the
# number of user accounts, an install id and the OS version to census.zorinos.com, and the
# installer's "Updates and other software" page has a "Don't participate in the census"
# checkbox that is off by default. NoctraOS does not report to Zorin, so:
#   - the installer always takes zorin-os-census out of the target (the three places that
#     read the checkbox now take that branch unconditionally),
#   - the checkbox and its text are hidden, not left as a choice that means nothing,
#   - the cron jobs and their state directory are gone from the image itself.
# Each edit must match exactly once; a changed upstream installer fails the build instead
# of quietly putting the census back.

strip_census() {
  local root="$1" cron
  python3 - "$root" <<'PY' || return 1
import pathlib, re, sys

root = pathlib.Path(sys.argv[1])
check = re.compile(r"if self\.db\.get\('ubiquity/no_zorin_os_census'\) == 'true':")
for rel in ("usr/share/ubiquity/install.py",
            "usr/share/ubiquity/plugininstall.py",
            "usr/lib/ubiquity/ubiquity/install_misc.py"):
    path = root / rel
    text, count = check.subn("if True:  # NoctraOS never installs the Zorin census", path.read_text())
    if count != 1:
        sys.exit(f"strip-census: expected one census check in {rel}, found {count}")
    path.write_text(text)

ui = root / "usr/share/ubiquity/gtk/stepPrepare.ui"
box = re.compile(r'(<object class="GtkBox" id="census_vbox">\s*)<property name="visible">True</property>')
text, count = box.subn(r'\1<property name="visible">False</property>\n'
                       r'            <property name="no_show_all">True</property>', ui.read_text())
if count != 1:
    sys.exit(f"strip-census: expected one census box in {ui.name}, found {count}")
ui.write_text(text)
PY
  for cron in etc/cron.daily/zorin-os-census etc/cron.hourly/zorin-os-census; do
    rm -f "$root/$cron"
  done
  rm -rf "$root/var/lib/zorin-os-census"
}
