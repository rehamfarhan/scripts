use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::config::{desktop_dir, IGNORE_DIRS};
use crate::model::WineOpts;

pub fn format_file_size(bytes: u64) -> String {
    if bytes >= 1024 * 1024 * 1024 {
        format!("{:.2} GB", bytes as f64 / (1024.0 * 1024.0 * 1024.0))
    } else if bytes >= 1024 * 1024 {
        format!("{:.2} MB", bytes as f64 / (1024.0 * 1024.0))
    } else if bytes >= 1024 {
        format!("{:.1} KB", bytes as f64 / 1024.0)
    } else {
        format!("{} B", bytes)
    }
}

pub fn evaluate_binary_score(game_dir: &Path, bin_path: &Path) -> (i32, &'static str) {
    let file_name = bin_path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase();

    let mut score = 50;

    let uninstaller_keywords = [
        "unins", "uninstall", "crash", "bugreport", "dxsetup", "vcredist", "redist", "setup",
        "update", "helper", "config", "tool", "editor", "launcher_backup",
    ];
    if uninstaller_keywords.iter().any(|&k| file_name.contains(k)) {
        score -= 200;
        return (score, "⚠️ Utility / Uninstaller");
    }

    let folder_name_clean = game_dir
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase()
        .replace(['_', '-'], "");

    let bin_clean = bin_path
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase()
        .replace(['_', '-'], "");

    if !bin_clean.is_empty()
        && (bin_clean.contains(&folder_name_clean) || folder_name_clean.contains(&bin_clean))
    {
        score += 150;
    }

    // Common native launcher script names
    if file_name == "start.sh"
        || file_name == "run.sh"
        || file_name == "launch.sh"
        || file_name == "start_game.sh"
    {
        score += 120;
    }

    // Binary architecture match
    if file_name.ends_with(".x86_64") || file_name.ends_with(".bin.x86_64") {
        score += 80;
    }

    if let Ok(metadata) = bin_path.metadata() {
        let size = metadata.len();
        if size > 10 * 1024 * 1024 {
            score += 40;
        } else if size > 2 * 1024 * 1024 {
            score += 20;
        }
    }

    let tag = if score >= 150 {
        "⭐ Recommended Main Binary"
    } else {
        "Executable"
    };
    (score, tag)
}

pub fn scan_executables(game_dir: &Path, max_depth: usize) -> Vec<PathBuf> {
    let mut executables = Vec::new();

    // Blacklisted non-executable extensions (even if chmod +x)
    let non_exec_exts = [
        "bmp", "png", "jpg", "jpeg", "gif", "ico", "svg", "webp", "tga", "dds",
        "pak", "dat", "pck", "assets", "asset", "res", "resource", "resources", "bank", "fsb", "unity3d", "bundle",
        "dll", "so", "dylib", "pdb", "config", "manifest", "hash", "info", "json", "xml", "txt", "md", "cfg", "ini", "log", "yaml", "yml",
        "wav", "ogg", "mp3", "flac", "mp4", "webm", "mkv", "avi",
        "ttf", "otf", "woff", "woff2",
    ];

    for entry in WalkDir::new(game_dir)
        .max_depth(max_depth)
        .into_iter()
        .filter_entry(|e| {
            let name = e.file_name().to_string_lossy();
            if e.file_type().is_dir() {
                !IGNORE_DIRS.contains(&name.as_ref()) && !name.starts_with('.')
            } else {
                true
            }
        })
        .filter_map(|e| e.ok())
    {
        let path = entry.path();
        if path.is_file() {
            let name_lower = path
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_lowercase();

            let ext = path
                .extension()
                .and_then(|e| e.to_str())
                .unwrap_or("")
                .to_lowercase();

            if name_lower == "start_game.sh" || non_exec_exts.contains(&ext.as_str()) {
                continue;
            }

            let is_windows_bin = name_lower.ends_with(".exe")
                || name_lower.ends_with(".bat")
                || name_lower.ends_with(".msi");

            let is_unix_exec = entry
                .metadata()
                .map(|m| (m.permissions().mode() & 0o111) != 0)
                .unwrap_or(false);

            if is_windows_bin || is_unix_exec {
                executables.push(path.to_path_buf());
            }
        }
    }

    executables.sort_by(|a, b| {
        let (score_a, _) = evaluate_binary_score(game_dir, a);
        let (score_b, _) = evaluate_binary_score(game_dir, b);
        let size_a = a.metadata().map(|m| m.len()).unwrap_or(0);
        let size_b = b.metadata().map(|m| m.len()).unwrap_or(0);

        score_b.cmp(&score_a).then_with(|| size_b.cmp(&size_a))
    });

    executables
}

pub fn create_launcher_script(
    game_dir: &Path,
    rel_binary: &Path,
    display_name: &str,
    is_windows: bool,
    wine_prefix: Option<&Path>,
    wine_opts: Option<&WineOpts>,
) -> std::io::Result<PathBuf> {
    let script_path = game_dir.join("start_game.sh");

    // Protect custom wrapper scripts
    if script_path.is_file() {
        if let Ok(content) = fs::read_to_string(&script_path) {
            if content.contains("# CUSTOM_WRAPPER")
                || content.contains("# MANUAL_OVERRIDE")
                || content.contains("# DO NOT OVERWRITE")
            {
                return Ok(script_path);
            }
        }
    }

    let icon = if is_windows { "💻" } else { "🐧" };
    let mut lines = vec![
        "#!/usr/bin/env bash".to_string(),
        format!("# GAME_NAME: {}", display_name),
        format!("# ICON: {}", icon),
        "# GENERATED BY RUN - AUTO-MANAGED".to_string(),
        "set -e".to_string(),
        "cd \"$(dirname \"$0\")\"".to_string(),
    ];

    let default_opts = WineOpts::default();
    let opts = wine_opts.unwrap_or(&default_opts);

    // Keyboard patch (keyd)
    if let Some(ref remap) = opts.keyd_remap {
        if !remap.trim().is_empty() {
            lines.push("".to_string());
            lines.push("# Keyboard Patch (keyd)".to_string());
            lines.push("if command -v keyd >/dev/null 2>&1; then".to_string());
            lines.push(format!("    keyd bind \"{}\" >/dev/null 2>&1 || true", remap));
            lines.push("    cleanup_keys() {".to_string());
            lines.push("        keyd reload >/dev/null 2>&1 || true".to_string());
            lines.push("    }".to_string());
            lines.push("    trap cleanup_keys EXIT INT TERM".to_string());
            lines.push("fi".to_string());
            lines.push("".to_string());
        }
    }

    // SDL Video Driver override
    if let Some(ref driver) = opts.sdl_driver {
        if driver == "x11" || driver == "wayland" {
            lines.push(format!("export SDL_VIDEODRIVER=\"{}\"", driver));
        }
    }

    let exec_prefix = if opts.keyd_remap.is_some() { "" } else { "exec " };

    if is_windows {
        if let Some(prefix) = wine_prefix {
            lines.push(format!("export WINEPREFIX=\"{}\"", prefix.display()));
        }
        if let Some(ref hud) = opts.dxvk_hud {
            lines.push(format!("export DXVK_HUD=\"{}\"", hud));
        }

        let safe_title: String = display_name
            .chars()
            .map(|c| if c.is_alphanumeric() { c } else { '_' })
            .collect();

        if let Some(ref res) = opts.resolution {
            lines.push(format!(
                "{}wine explorer /desktop={},{} \"{}\" \"$@\"",
                exec_prefix,
                safe_title,
                res,
                rel_binary.display()
            ));
        } else {
            lines.push(format!(
                "{}wine \"{}\" \"$@\"",
                exec_prefix,
                rel_binary.display()
            ));
        }
    } else {
        lines.push(format!(
            "{}\"./{}\" \"$@\"",
            exec_prefix,
            rel_binary.display()
        ));
    }

    let content = lines.join("\n") + "\n";
    fs::write(&script_path, content)?;

    let mut perms = fs::metadata(&script_path)?.permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&script_path, perms)?;

    Ok(script_path)
}

pub fn create_desktop_entry(
    display_name: &str,
    launcher_script: &Path,
) -> std::io::Result<PathBuf> {
    let desk_dir = desktop_dir();
    fs::create_dir_all(&desk_dir)?;

    let safe_id: String = display_name
        .to_lowercase()
        .chars()
        .map(|c| if c.is_alphanumeric() || c == '_' || c == '-' { c } else { '_' })
        .collect();

    let desktop_path = desk_dir.join(format!("game_{}.desktop", safe_id.trim_matches('_')));
    let script_abs = launcher_script
        .canonicalize()
        .unwrap_or_else(|_| launcher_script.to_path_buf());

    let content = format!(
        "[Desktop Entry]\nType=Application\nName={}\nExec={}\nIcon=applications-games\nTerminal=false\nCategories=Game;\nComment=Launched via Run Game Launcher\n",
        display_name,
        script_abs.display()
    );

    fs::write(&desktop_path, content)?;
    Ok(desktop_path)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_file_size() {
        assert_eq!(format_file_size(500), "500 B");
        assert_eq!(format_file_size(2048), "2.0 KB");
        assert_eq!(format_file_size(10 * 1024 * 1024), "10.00 MB");
        assert_eq!(format_file_size(2 * 1024 * 1024 * 1024), "2.00 GB");
    }

    #[test]
    fn test_binary_heuristics() {
        let (score_unins, tag_unins) = evaluate_binary_score(Path::new("/games/test"), Path::new("/games/test/unins000.exe"));
        assert!(score_unins < 0);
        assert!(tag_unins.contains("Uninstaller"));

        let (score_match, tag_match) = evaluate_binary_score(Path::new("/games/balatro"), Path::new("/games/balatro/Balatro.exe"));
        assert!(score_match >= 150);
        assert_eq!(tag_match, "⭐ Recommended Main Binary");
    }
}

