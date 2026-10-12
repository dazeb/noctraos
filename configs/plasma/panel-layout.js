// NoctraOS Plasma layout v1 (flavour kubuntu): one bottom panel with the Application Launcher, pinned apps, the system tray
// and the clock. Applied once per account by apply-layout.sh through plasmashell's scripting D-Bus API.
var existing = panels();
for (var i = 0; i < existing.length; i++) {
    existing[i].remove();
}
var panel = new Panel();
panel.location = "bottom";
panel.height = 44;
panel.alignment = "center";
panel.lengthMode = "fill";
panel.floating = true;

panel.addWidget("org.kde.plasma.kickoff");
var tasks = panel.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", [
    "applications:org.kde.dolphin.desktop",
    "applications:org.kde.konsole.desktop",
    "applications:code.desktop",
    "applications:noctraos-hermes.desktop",
    "applications:noctraos-control.desktop"
]);
panel.addWidget("org.kde.plasma.marginsseparator");
panel.addWidget("org.kde.plasma.systemtray");
panel.addWidget("org.kde.plasma.digitalclock");
panel.addWidget("org.kde.plasma.showdesktop");
