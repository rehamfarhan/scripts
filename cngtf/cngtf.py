#!/usr/bin/env python3
import sys
import os
import shutil
import subprocess
import re
import argparse
from pathlib import Path

HOME = Path.home()
CONFIG_DIR = HOME / ".config"

def backup_file(path: Path):
    """Creates a .bak backup of the target file if it exists."""
    if path.exists() and path.is_file():
        backup_path = path.with_suffix(path.suffix + ".bak")
        try:
            shutil.copy2(path, backup_path)
            print(f"  [Backup] Created {backup_path}")
        except Exception as e:
            print(f"  [Warning] Failed to backup {path}: {e}")

def get_installed_fonts():
    """Gets a sorted list of unique installed font family names via fc-list."""
    try:
        res = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True, check=True)
        fonts = set()
        for line in res.stdout.splitlines():
            for family in line.split(","):
                family = family.strip()
                if family:
                    fonts.add(family)
        return sorted(list(fonts))
    except Exception as e:
        print(f"[Error] Failed to fetch system fonts: {e}")
        sys.exit(1)

def get_installed_emoji_fonts():
    """Gets a sorted list of installed emoji font family names."""
    fonts = set()
    
    # Method 1: Query fonts marked with color=true in fontconfig
    try:
        res = subprocess.run(["fc-list", ":color=true", "family"], capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            for family in line.split(","):
                family = family.strip()
                # Exclude non-emoji fonts like musical notation
                if family and not any(skip in family.lower() for skip in ["music", "notation", "znamenny"]):
                    fonts.add(family)
    except Exception:
        pass

    # Method 2: Also scan all system fonts for known emoji keywords (e.g. Mutant, Blobmoji, Emoji)
    all_fonts = get_installed_fonts()
    for f in all_fonts:
        f_lower = f.lower()
        if "emoji" in f_lower or "mutant" in f_lower or "blob" in f_lower or "twemoji" in f_lower or "tossface" in f_lower:
            fonts.add(f)

    return sorted(list(fonts))

def select_font_with_fzf(fonts, header="Select a Systemwide Font:"):
    """Launches fzf to interactively select a font."""
    if not shutil.which("fzf"):
        print("[Error] 'fzf' is not installed on this system. Please specify a font name as an argument.")
        sys.exit(1)
    
    font_input = "\n".join(fonts)
    try:
        process = subprocess.Popen(
            ["fzf", f"--header={header}", "--prompt=Font > ", "--height=40%", "--layout=reverse", "--border"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
        selected_font, _ = process.communicate(input=font_input)
        if process.returncode != 0 or not selected_font.strip():
            print("[Info] Selection canceled.")
            sys.exit(0)
        return selected_font.strip()
    except Exception as e:
        print(f"[Error] Failed running fzf: {e}")
        sys.exit(1)

def validate_font(font_name, installed_fonts):
    """Checks if the font exists in installed fonts."""
    installed_lower = {f.lower(): f for f in installed_fonts}
    if font_name.lower() in installed_lower:
        return installed_lower[font_name.lower()]
    print(f"[Warning] '{font_name}' was not explicitly matched in fc-list, but proceeding as requested.")
    return font_name

def update_emoji_fontconfig(emoji_font):
    print("-> Updating Fontconfig emoji configuration...")
    fc_dir = CONFIG_DIR / "fontconfig"
    fc_dir.mkdir(parents=True, exist_ok=True)
    
    fonts_conf = fc_dir / "fonts.conf"
    if fonts_conf.exists():
        backup_file(fonts_conf)
        content = fonts_conf.read_text()
        
        # Update <family>emoji</family> prefer block
        if "<family>emoji</family>" in content:
            content = re.sub(
                r'(<family>emoji</family>\s*<prefer>\s*<family>)[^<]+',
                rf'\g<1>{emoji_font}',
                content
            )
        else:
            emoji_block = f"""  <alias binding="same">
    <family>emoji</family>
    <prefer>
      <family>{emoji_font}</family>
      <family>Noto Color Emoji</family>
    </prefer>
  </alias>
"""
            content = content.replace("<fontconfig>", f"<fontconfig>\n{emoji_block}", 1)
        
        # Update match rule for emoji family
        if '<test qual="any" name="family"><string>emoji</string></test>' in content:
            content = re.sub(
                r'(<test qual="any" name="family"><string>emoji</string></test>\s*<edit name="family" mode="assign" binding="same"><string>)[^<]+',
                rf'\g<1>{emoji_font}',
                content
            )
        else:
            match_block = f"""  <match target="pattern">
    <test qual="any" name="family"><string>emoji</string></test>
    <edit name="family" mode="assign" binding="same"><string>{emoji_font}</string></edit>
  </match>
"""
            content = content.replace("</fontconfig>", f"{match_block}</fontconfig>")
            
        # Update weak append in pattern match if present
        if '<edit name="family" mode="append" binding="weak">' in content:
            content = re.sub(
                r'(<edit name="family" mode="append" binding="weak">\s*<string>)[^<]+',
                rf'\g<1>{emoji_font}',
                content
            )
            
        fonts_conf.write_text(content)
    else:
        # Create minimal fontconfig if fonts.conf doesn't exist yet
        content = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <alias binding="same">
    <family>emoji</family>
    <prefer>
      <family>{emoji_font}</family>
      <family>Noto Color Emoji</family>
    </prefer>
  </alias>
  <match target="pattern">
    <test qual="any" name="family"><string>emoji</string></test>
    <edit name="family" mode="assign" binding="same"><string>{emoji_font}</string></edit>
  </match>
</fontconfig>
"""
        fonts_conf.write_text(content)
    print(f"  [OK] Emoji font set to '{emoji_font}'.")

def update_fontconfig(font_name):
    print("-> Updating Fontconfig configuration...")
    fc_dir = CONFIG_DIR / "fontconfig"
    fc_dir.mkdir(parents=True, exist_ok=True)
    
    fonts_conf = fc_dir / "fonts.conf"
    backup_file(fonts_conf)
    
    # Read existing emoji preference if available
    current_emoji = "Fluent Emoji Color"
    if fonts_conf.exists():
        try:
            m = re.search(r'<family>emoji</family>\s*<prefer>\s*<family>([^<]+)', fonts_conf.read_text())
            if m:
                current_emoji = m.group(1).strip()
        except Exception:
            pass
    
    content = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <alias binding="same">
    <family>emoji</family>
    <prefer>
      <family>{current_emoji}</family>
      <family>Noto Color Emoji</family>
    </prefer>
  </alias>

  <match target="pattern">
    <test qual="any" name="family"><string>emoji</string></test>
    <edit name="family" mode="assign" binding="same"><string>{current_emoji}</string></edit>
  </match>

  <!-- Append Emoji font as fallback for sans/serif/monospace -->
  <alias>
    <family>sans-serif</family>
    <prefer>
      <family>{font_name}</family>
      <family>{current_emoji}</family>
    </prefer>
  </alias>
  <alias>
    <family>monospace</family>
    <prefer>
      <family>{font_name}</family>
      <family>{current_emoji}</family>
    </prefer>
  </alias>

  <!-- Universal strong match: Prepend chosen font to any requested pattern -->
  <match target="pattern">
    <edit name="family" mode="prepend" binding="strong">
      <string>{font_name}</string>
    </edit>
    <edit name="family" mode="append" binding="weak">
      <string>{current_emoji}</string>
    </edit>
  </match>

  <!-- Font rendering optimizations -->
  <match target="font">
    <edit name="antialias" mode="assign"><bool>true</bool></edit>
    <edit name="hinting" mode="assign"><bool>true</bool></edit>
    <edit name="hintstyle" mode="assign"><const>hintslight</const></edit>
    <edit name="rgba" mode="assign"><const>rgb</const></edit>
    <edit name="lcdfilter" mode="assign"><const>lcddefault</const></edit>
  </match>
</fontconfig>
"""
    fonts_conf.write_text(content)
    
    conf_d = fc_dir / "conf.d"
    conf_d.mkdir(parents=True, exist_ok=True)
    dusky_conf = conf_d / "99-dusky-fonts.conf"
    backup_file(dusky_conf)
    
    dusky_content = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <alias binding="strong">
    <family>sans-serif</family>
    <prefer>
      <family>{font_name}</family>
    </prefer>
  </alias>
  <alias binding="strong">
    <family>serif</family>
    <prefer>
      <family>{font_name}</family>
    </prefer>
  </alias>
  <alias binding="strong">
    <family>monospace</family>
    <prefer>
      <family>{font_name}</family>
    </prefer>
  </alias>
</fontconfig>
"""
    dusky_conf.write_text(dusky_content)
    print("  [OK] Fontconfig updated.")

def update_gsettings(font_name, font_size):
    print("-> Updating GSettings desktop interface...")
    font_spec = f"{font_name} {font_size}"
    keys = [
        "font-name",
        "document-font-name",
        "monospace-font-name",
        "titlebar-font"
    ]
    for key in keys:
        try:
            subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", key, font_spec], stderr=subprocess.DEVNULL)
        except Exception:
            pass
    print("  [OK] GSettings updated.")

def update_gtk_configs(font_name, font_size):
    print("-> Updating GTK 3 & GTK 4 configurations...")
    font_spec = f"{font_name} {font_size}"
    for gtk_ver in ["gtk-3.0", "gtk-4.0"]:
        gtk_dir = CONFIG_DIR / gtk_ver
        if not gtk_dir.exists():
            continue
        settings_ini = gtk_dir / "settings.ini"
        if settings_ini.exists():
            backup_file(settings_ini)
            content = settings_ini.read_text()
            if "gtk-font-name=" in content:
                content = re.sub(r"^gtk-font-name=.*$", f"gtk-font-name={font_spec}", content, flags=re.MULTILINE)
            else:
                if "[Settings]" in content:
                    content = content.replace("[Settings]\n", f"[Settings]\ngtk-font-name={font_spec}\n")
                else:
                    content += f"\n[Settings]\ngtk-font-name={font_spec}\n"
            settings_ini.write_text(content)
    print("  [OK] GTK configs updated.")

def update_qt_configs(font_name, font_size):
    print("-> Updating Qt5 & Qt6 qt5ct/qt6ct configurations...")
    qt5_conf = CONFIG_DIR / "qt5ct" / "qt5ct.conf"
    if qt5_conf.exists():
        backup_file(qt5_conf)
        content = qt5_conf.read_text()
        content = re.sub(r'^fixed=.*$', f'fixed="{font_name},{font_size},-1,5,50,0,0,0,0,0"', content, flags=re.MULTILINE)
        content = re.sub(r'^general=.*$', f'general="{font_name},{font_size},-1,5,50,0,0,0,0,0"', content, flags=re.MULTILINE)
        qt5_conf.write_text(content)
        
    qt6_conf = CONFIG_DIR / "qt6ct" / "qt6ct.conf"
    if qt6_conf.exists():
        backup_file(qt6_conf)
        content = qt6_conf.read_text()
        content = re.sub(r'^fixed=.*$', f'fixed="{font_name},{font_size},-1,5,400,0,0,0,0,0,0,0,0,0,0,1"', content, flags=re.MULTILINE)
        content = re.sub(r'^general=.*$', f'general="{font_name},{font_size},-1,5,400,0,0,0,0,0,0,0,0,0,0,1"', content, flags=re.MULTILINE)
        qt6_conf.write_text(content)
    print("  [OK] Qt configs updated.")

def update_xsettingsd(font_name, font_size):
    print("-> Updating xsettingsd configuration...")
    xset_conf = CONFIG_DIR / "xsettingsd" / "xsettingsd.conf"
    if xset_conf.exists():
        backup_file(xset_conf)
        content = xset_conf.read_text()
        if "Gtk/FontName" in content:
            content = re.sub(r'^Gtk/FontName\s+.*$', f'Gtk/FontName "{font_name} {font_size}"', content, flags=re.MULTILINE)
        else:
            content += f'\nGtk/FontName "{font_name} {font_size}"\n'
        xset_conf.write_text(content)
        print("  [OK] xsettingsd updated.")

def update_kdeglobals(font_name, font_size):
    print("-> Updating KDE Globals configuration...")
    kde_conf = CONFIG_DIR / "kdeglobals"
    if kde_conf.exists():
        backup_file(kde_conf)
        content = kde_conf.read_text()
        font_str = f"{font_name},{font_size},-1,5,50,0,0,0,0,0"
        small_font_str = f"{font_name},{max(font_size - 2, 7)},-1,5,50,0,0,0,0,0"
        
        for key in ["font", "fixed", "menuFont", "toolBarFont"]:
            if f"{key}=" in content:
                content = re.sub(rf"^{key}=.*$", f"{key}={font_str}", content, flags=re.MULTILINE)
            else:
                if "[General]" in content:
                    content = content.replace("[General]\n", f"[General]\n{key}={font_str}\n")
        if "smallestReadableFont=" in content:
            content = re.sub(r"^smallestReadableFont=.*$", f"smallestReadableFont={small_font_str}", content, flags=re.MULTILINE)
            
        kde_conf.write_text(content)
        print("  [OK] kdeglobals updated.")

def update_rofi(font_name, font_size):
    print("-> Updating Rofi launcher configuration...")
    rofi_conf = CONFIG_DIR / "rofi" / "config.rasi"
    if rofi_conf.exists():
        backup_file(rofi_conf)
        content = rofi_conf.read_text()
        content = re.sub(r'font:\s*"[^"]*11";', f'font:           "{font_name} {font_size}";', content)
        content = re.sub(r'font:\s*"[^"]*Bold 11";', f'font:               "{font_name} Bold {font_size}";', content)
        content = re.sub(r'font:\s*"[^"]*9";', f'font:               "{font_name} {max(font_size - 2, 7)}";', content)
        rofi_conf.write_text(content)
        print("  [OK] Rofi config updated.")

def update_waybar(font_name):
    print("-> Updating Waybar CSS configurations...")
    waybar_dir = CONFIG_DIR / "waybar"
    if waybar_dir.exists():
        styles = list(waybar_dir.glob("**/style.css"))
        for style_file in styles:
            try:
                content = style_file.read_text()
                if "font-family:" in content:
                    new_content = re.sub(r'font-family:\s*[^;]+;', f'font-family: "{font_name}", sans-serif;', content, count=1)
                    if new_content != content:
                        backup_file(style_file)
                        style_file.write_text(new_content)
            except Exception:
                pass
        print("  [OK] Waybar style CSS updated.")

def update_kitty(font_name, font_size):
    print("-> Updating Kitty terminal configuration...")
    kitty_conf = CONFIG_DIR / "kitty" / "kitty.conf"
    if kitty_conf.exists():
        backup_file(kitty_conf)
        content = kitty_conf.read_text()
        content = re.sub(r'^font_family\s+.*$', f'font_family      {font_name}', content, flags=re.MULTILINE)
        content = re.sub(r'^font_size\s+.*$', f'font_size {font_size}.0', content, flags=re.MULTILINE)
        kitty_conf.write_text(content)
        print("  [OK] Kitty terminal config updated.")

def update_foot(font_name, font_size):
    print("-> Updating Foot terminal configuration...")
    foot_conf = CONFIG_DIR / "foot" / "foot.ini"
    if foot_conf.exists():
        backup_file(foot_conf)
        content = foot_conf.read_text()
        content = re.sub(r'^font=[^:\n]+', f'font={font_name}', content, flags=re.MULTILINE)
        foot_conf.write_text(content)
        print("  [OK] Foot terminal config updated.")

def update_hyprland(font_name):
    print("-> Updating Hyprland appearance configuration...")
    appearance_lua = CONFIG_DIR / "hypr" / "source" / "appearance.lua"
    if appearance_lua.exists():
        backup_file(appearance_lua)
        content = appearance_lua.read_text()
        content = re.sub(r'font_family\s*=\s*"[^"]*"', f'font_family = "{font_name}"', content)
        appearance_lua.write_text(content)
        print("  [OK] Hyprland appearance updated.")

def refresh_system():
    print("-> Rebuilding font cache and signaling desktop services...")
    subprocess.run(["fc-cache", "-f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-HUP", "xsettingsd"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-USR2", "waybar"], stderr=subprocess.DEVNULL)
    print("  [OK] System font cache & services refreshed.")

def main():
    parser = argparse.ArgumentParser(description="Systemwide Font Changer for Linux/Hyprland (cngtf)")
    parser.add_argument("font", nargs="?", help="Name of the font to apply (launches fzf menu if omitted)")
    parser.add_argument("--size", type=int, default=11, help="Font size to set (default: 11)")
    parser.add_argument("-e", "--emoji", action="store_true", help="Change systemwide emoji font preference instead")
    args = parser.parse_args()

    if args.emoji:
        emoji_fonts = get_installed_emoji_fonts()
        if not args.font:
            selected_font = select_font_with_fzf(emoji_fonts, header="Select an Emoji Font:")
        else:
            selected_font = validate_font(args.font, emoji_fonts)

        print(f"\n==================================================")
        print(f" Applying Systemwide Emoji Font: '{selected_font}'")
        print(f"==================================================\n")

        update_emoji_fontconfig(selected_font)
        refresh_system()
        print(f"\n[Success] Systemwide emoji font changed to '{selected_font}' successfully!\n")
        return

    installed_fonts = get_installed_fonts()

    if not args.font:
        selected_font = select_font_with_fzf(installed_fonts)
    else:
        selected_font = validate_font(args.font, installed_fonts)

    print(f"\n==================================================")
    print(f" Applying Systemwide Font: '{selected_font}' (size: {args.size})")
    print(f"==================================================\n")

    update_fontconfig(selected_font)
    update_gsettings(selected_font, args.size)
    update_gtk_configs(selected_font, args.size)
    update_qt_configs(selected_font, args.size)
    update_xsettingsd(selected_font, args.size)
    update_kdeglobals(selected_font, args.size)
    update_rofi(selected_font, args.size)
    update_waybar(selected_font)
    update_kitty(selected_font, args.size)
    update_foot(selected_font, args.size)
    update_hyprland(selected_font)
    refresh_system()

    print(f"\n[Success] Systemwide font changed to '{selected_font}' successfully!\n")

if __name__ == "__main__":
    main()
