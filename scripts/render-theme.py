#!/usr/bin/env python3
"""Render desktop/app defaults from one palette; --check detects drift."""
import argparse
import json
from pathlib import Path
import re
from string import Template


def render(root):
    theme = root / "configs/theme"
    palette = json.loads((theme / "palette.json").read_text())
    colors = palette["colors"]
    for color in [*colors.values(), *palette["terminal"]]:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError(f"Invalid palette color: {color}")
    if len(palette["terminal"]) != 16:
        raise ValueError("The terminal palette must have 16 colors")
    values = {**colors, "font": palette["font"], "radius": palette["radius"]}
    outputs = {}
    for name in ["gnome-shell.css", "gtk.css"]:
        outputs[theme / name] = Template((theme / (name + ".in")).read_text()).substitute(values)
    herdr = {"panel_bg": "background", "sidebar_bg": "panel",
             "active_row_bg": "raised", "selection_bg": "selection",
             "text": "foreground", "subtext0": "muted", "accent": "accent",
             "mauve": "magenta", "green": "green", "blue": "blue",
             "red": "red", "yellow": "yellow"}
    outputs[theme / "herdr.toml"] = '[theme]\nname = "terminal"\n\n[theme.custom]\n' + "".join(
        f'{key} = "{colors[value]}"\n' for key, value in herdr.items())
    btop = {"main_bg": "background", "main_fg": "foreground", "title": "accent",
            "hi_fg": "accent", "selected_bg": "selection", "selected_fg": "foreground",
            "inactive_fg": "muted", "graph_text": "foreground", "meter_bg": "raised",
            "proc_misc": "muted", "cpu_box": "accent", "mem_box": "foreground",
            "net_box": "foreground", "proc_box": "foreground", "div_line": "border",
            "temp_start": "foreground", "temp_mid": "accent", "temp_end": "red",
            "cpu_start": "border", "cpu_mid": "foreground", "cpu_end": "accent",
            "free_start": "border", "free_mid": "foreground", "free_end": "accent"}
    outputs[theme / "noctraos-btop.theme"] = "".join(
        f'theme[{key}]="{colors[value]}"\n' for key, value in btop.items())
    editor = {"editor.background": "background", "editor.foreground": "foreground",
              "editorCursor.foreground": "accent", "editor.selectionBackground": "selection",
              "editor.lineHighlightBackground": "raised", "editorLineNumber.foreground": "muted",
              "sideBar.background": "panel", "sideBar.foreground": "foreground",
              "sideBar.border": "border", "activityBar.background": "panel",
              "activityBar.foreground": "foreground", "activityBar.activeBorder": "accent",
              "statusBar.background": "panel", "statusBar.foreground": "foreground",
              "titleBar.activeBackground": "panel", "titleBar.activeForeground": "foreground",
              "tab.activeBackground": "background", "tab.inactiveBackground": "panel",
              "tab.activeBorderTop": "accent", "focusBorder": "accent",
              "input.background": "raised", "input.foreground": "foreground",
              "input.border": "border", "button.background": "accent",
              "button.foreground": "panel", "list.activeSelectionBackground": "selection",
              "list.activeSelectionForeground": "foreground", "panel.border": "border",
              "terminal.background": "background", "terminal.foreground": "foreground",
              "terminalCursor.foreground": "accent",
              "textLink.foreground": "accent", "textLink.activeForeground": "foreground",
              "progressBar.background": "accent", "badge.background": "accent",
              "badge.foreground": "panel", "statusBarItem.remoteBackground": "raised",
              "statusBarItem.remoteForeground": "accent"}
    editor_colors = {key: colors[value] for key, value in editor.items()}
    ansi = ["Black", "Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"]
    for index, color in enumerate(palette["terminal"]):
        key = "terminal.ansi" + ("Bright" if index >= 8 else "") + ansi[index % 8]
        editor_colors[key] = color
    settings = {"editor.fontFamily": f"'{palette['font']}', monospace",
                "editor.fontLigatures": True, "editor.fontSize": 13,
                "workbench.colorTheme": "Default Dark Modern",
                "workbench.colorCustomizations": editor_colors,
                "editor.formatOnSave": True, "files.autoSave": "afterDelay",
                "terminal.integrated.fontFamily": palette["font"],
                "git.enableSmartCommit": True, "extensions.autoCheckUpdates": True}
    outputs[root / "configs/vscode/settings.json"] = json.dumps(settings, indent=2) + "\n"
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    stale = []
    for path, content in render(root).items():
        if path.exists() and path.read_text() == content:
            continue
        if args.check:
            stale.append(str(path.relative_to(root)))
        else:
            path.write_text(content)
            print(f"Rendered {path.relative_to(root)}")
    if stale:
        parser.exit(1, "Theme outputs need regeneration: " + ", ".join(stale) + "\n")


if __name__ == "__main__":
    main()
