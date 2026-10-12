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
    outputs.update(render_plasma(root, palette))
    return outputs


def rgb(color):
    """'#e68e0d' -> '230,142,13', the form KDE colour schemes and Konsole use."""
    return ",".join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))


def render_plasma(root, palette):
    """The KDE colour scheme, the Konsole colour scheme and the Konsole profile (flavour kubuntu), from the same palette."""
    c = palette["colors"]
    plasma = root / "configs/plasma"

    def colors(section, bg, alt, fg):
        return (f"[Colors:{section}]\nBackgroundAlternate={rgb(c[alt])}\nBackgroundNormal={rgb(c[bg])}\n"
                f"DecorationFocus={rgb(c['accent'])}\nDecorationHover={rgb(c['accent'])}\n"
                f"ForegroundActive={rgb(c['accent'])}\nForegroundInactive={rgb(c['muted'])}\n"
                f"ForegroundLink={rgb(c['accent'])}\nForegroundNegative={rgb(c['red'])}\n"
                f"ForegroundNeutral={rgb(c['yellow'])}\nForegroundNormal={rgb(c[fg])}\n"
                f"ForegroundPositive={rgb(c['green'])}\nForegroundVisited={rgb(c['muted'])}\n\n")

    scheme = "[ColorEffects:Disabled]\nChangeSelectionColor=\nColor=56,56,56\nColorAmount=0\nColorEffect=0\n"
    scheme += "ContrastAmount=0.65\nContrastEffect=1\nEnable=\nIntensityAmount=0.1\nIntensityEffect=2\n\n"
    scheme += "[ColorEffects:Inactive]\nChangeSelectionColor=true\nColor=112,111,110\nColorAmount=0.025\n"
    scheme += "ColorEffect=2\nContrastAmount=0.1\nContrastEffect=2\nEnable=false\nIntensityAmount=0\nIntensityEffect=0\n\n"
    scheme += colors("Button", "raised", "selection", "foreground")
    scheme += colors("Complementary", "panel", "background", "foreground")
    scheme += colors("Header", "panel", "background", "foreground")
    selection = colors("Selection", "accent", "accent", "panel")
    selection = selection.replace(f"ForegroundActive={rgb(c['accent'])}", f"ForegroundActive={rgb(c['panel'])}")
    selection = selection.replace(f"ForegroundInactive={rgb(c['muted'])}", f"ForegroundInactive={rgb(c['panel'])}")
    selection = selection.replace(f"ForegroundLink={rgb(c['accent'])}", f"ForegroundLink={rgb(c['panel'])}")
    scheme += selection
    scheme += colors("Tooltip", "raised", "selection", "foreground")
    scheme += colors("View", "background", "raised", "foreground")
    scheme += colors("Window", "background", "raised", "foreground")
    scheme += "[General]\nColorScheme=NoctraOSDark\nName=NoctraOS Dark\nshadeSortColumn=true\n\n"
    scheme += f"[KDE]\ncontrast=4\n\n[WM]\nactiveBackground={rgb(c['panel'])}\nactiveBlend={rgb(c['foreground'])}\n"
    scheme += f"activeForeground={rgb(c['foreground'])}\ninactiveBackground={rgb(c['panel'])}\n"
    scheme += f"inactiveBlend={rgb(c['muted'])}\ninactiveForeground={rgb(c['muted'])}\n"

    term = palette["terminal"]
    names = ["", "Intense"]
    konsole = f"[Background]\nColor={rgb(c['background'])}\n\n[BackgroundIntense]\nColor={rgb(c['raised'])}\n\n"
    konsole += f"[BackgroundFaint]\nColor={rgb(c['background'])}\n\n"
    for index, color in enumerate(term):
        konsole += f"[Color{index % 8}{names[index // 8]}]\nColor={rgb(color)}\n\n"
    konsole += f"[Foreground]\nColor={rgb(c['foreground'])}\n\n[ForegroundIntense]\nColor={rgb(term[15])}\n\n"
    konsole += f"[ForegroundFaint]\nColor={rgb(c['muted'])}\n\n[General]\nDescription=NoctraOS\nOpacity=1\n"

    profile = ("[Appearance]\nColorScheme=NoctraOS\n"
               f"Font={palette['font']},11,-1,5,50,0,0,0,0,0\n\n[General]\nName=NoctraOS\nParent=FALLBACK/\n\n"
               "[Scrolling]\nHistorySize=10000\n")
    return {plasma / "NoctraOSDark.colors": scheme,
            plasma / "konsole/NoctraOS.colorscheme": konsole,
            plasma / "konsole/NoctraOS.profile": profile}


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
