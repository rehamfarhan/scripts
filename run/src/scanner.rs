use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::config::{desktop_dir, IGNORE_DIRS};
use crate::model::WineOpts;

const ENV_BLOCK_START: &str = "# >>> RUN-MANAGED:ENV — auto-updated on settings change, do not hand-edit between these lines >>>";
const ENV_BLOCK_END: &str = "# <<< RUN-MANAGED:ENV <<<";

/// Result of a create_launcher_script call.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ScriptGenerationResult {
    /// Script did not exist; generated fresh with markers.
    Generated,
    /// Existing script had valid markers; env block was patched in-place.
    Patched,
    /// Existing script had missing, duplicated, or misordered markers.
    /// File was left completely untouched.
    SkippedCorruptMarkers,
}

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

/// Generate only the settings-driven env block content (keyd, SDL, WINEPREFIX, DXVK_HUD).
/// This is what goes between the markers. Does NOT include the launch line or exit $?.
fn generate_env_block(
    opts: &WineOpts,
    is_windows: bool,
    wine_prefix: Option<&Path>,
) -> Vec<String> {
    let mut block = Vec::new();

    // Keyboard patch (keyd)
    if let Some(ref remap) = opts.keyd_remap {
        if !remap.trim().is_empty() {
            block.push("# Keyboard Patch (keyd)".to_string());
            block.push("if command -v keyd >/dev/null 2>&1; then".to_string());
            block.push(format!("    keyd bind \"{}\" >/dev/null 2>&1 || true", remap));
            block.push("    cleanup_keys() {".to_string());
            block.push("        keyd reload >/dev/null 2>&1 || true".to_string());
            block.push("    }".to_string());
            block.push("    trap cleanup_keys EXIT INT TERM".to_string());
            block.push("fi".to_string());
        }
    }

    // SDL Video Driver override
    if let Some(ref driver) = opts.sdl_driver {
        if driver == "x11" || driver == "wayland" {
            block.push(format!("export SDL_VIDEODRIVER=\"{}\"", driver));
        }
    }

    // Wine-specific exports (only for Windows games)
    if is_windows {
        if let Some(prefix) = wine_prefix {
            block.push(format!("export WINEPREFIX=\"{}\"", prefix.display()));
        }
        if let Some(ref hud) = opts.dxvk_hud {
            block.push(format!("export DXVK_HUD=\"{}\"", hud));
        }
    }

    block
}

/// Generate the frozen (non-env) parts of the script: shebang, headers, cd, launch line, exit.
/// Resolution is part of the launch line (wine explorer /desktop=...) and is frozen —
/// it is NOT patchable via the env block, to avoid re-opening the launch-line clobbering problem.
fn generate_frozen_lines(
    display_name: &str,
    rel_binary: &Path,
    is_windows: bool,
    opts: &WineOpts,
) -> Vec<String> {
    let icon = if is_windows { "💻" } else { "🐧" };
    let mut lines = vec![
        "#!/usr/bin/env bash".to_string(),
        format!("# GAME_NAME: {}", display_name),
        format!("# ICON: {}", icon),
        "set -e".to_string(),
        "cd \"$(dirname \"$0\")\"".to_string(),
    ];

    // Launch line — resolution is embedded here and frozen
    if is_windows {
        let safe_title: String = display_name
            .chars()
            .map(|c| if c.is_alphanumeric() { c } else { '_' })
            .collect();

        if let Some(ref res) = opts.resolution {
            lines.push(format!(
                "wine explorer /desktop={},{} \"{}\" \"$@\"",
                safe_title,
                res,
                rel_binary.display()
            ));
        } else {
            lines.push(format!(
                "wine \"{}\" \"$@\"",
                rel_binary.display()
            ));
        }
    } else {
        lines.push(format!(
            "\"./{}\" \"$@\"",
            rel_binary.display()
        ));
    }

    // Ensure script exit code reflects the game's exit code
    lines.push("exit $?".to_string());

    lines
}

/// Attempt to patch the env block in an existing script file.
/// Returns Ok(true) if patched, Ok(false) if markers were corrupt (file untouched).
fn patch_env_block(
    existing_content: &str,
    new_block: &Vec<String>,
) -> Result<String, ()> {
    let start_count = existing_content.matches(ENV_BLOCK_START).count();
    let end_count = existing_content.matches(ENV_BLOCK_END).count();

    // Markers must exist exactly once each, in the right order
    if start_count != 1 || end_count != 1 {
        return Err(());
    }

    let start_idx = existing_content.find(ENV_BLOCK_START).unwrap();
    let end_idx = existing_content.find(ENV_BLOCK_END).unwrap();

    if start_idx >= end_idx {
        return Err(());
    }

    // Find the end of the start marker line (including its newline)
    let start_line_end = existing_content[start_idx..]
        .find('\n')
        .map(|i| start_idx + i + 1)
        .unwrap_or(existing_content.len());

    // The end marker line starts at end_idx; we want to include the full end marker line
    let end_line_end = existing_content[end_idx..]
        .find('\n')
        .map(|i| end_idx + i + 1)
        .unwrap_or(existing_content.len());

    // Build the new block content
    let block_content = if new_block.is_empty() {
        String::new()
    } else {
        let mut s = new_block.join("\n");
        s.push('\n');
        s
    };

    // Splice: everything before start marker + start marker line + new block + end marker line + everything after
    let mut result = String::with_capacity(existing_content.len() + block_content.len());
    result.push_str(&existing_content[..start_line_end]);
    result.push_str(&block_content);
    result.push_str(&existing_content[end_idx..end_line_end]);
    result.push_str(&existing_content[end_line_end..]);

    Ok(result)
}

pub fn create_launcher_script(
    game_dir: &Path,
    rel_binary: &Path,
    display_name: &str,
    is_windows: bool,
    wine_prefix: Option<&Path>,
    wine_opts: Option<&WineOpts>,
) -> std::io::Result<(PathBuf, ScriptGenerationResult)> {
    let script_path = game_dir.join("start_game.sh");
    let default_opts = WineOpts::default();
    let opts = wine_opts.unwrap_or(&default_opts);

    let result = if script_path.is_file() {
        // Existing file — attempt marker-based patch
        let content = fs::read_to_string(&script_path)?;
        let env_block = generate_env_block(opts, is_windows, wine_prefix);

        match patch_env_block(&content, &env_block) {
            Ok(new_content) => {
                fs::write(&script_path, new_content)?;
                ScriptGenerationResult::Patched
            }
            Err(()) => {
                // Corrupt markers — leave file untouched, ensure executable
                if let Ok(metadata) = fs::metadata(&script_path) {
                    let mut perms = metadata.permissions();
                    perms.set_mode(0o755);
                    let _ = fs::set_permissions(&script_path, perms);
                }
                return Ok((script_path, ScriptGenerationResult::SkippedCorruptMarkers));
            }
        }
    } else {
        // New file — generate fresh with markers
        let mut lines = generate_frozen_lines(display_name, rel_binary, is_windows, opts);

        // Insert the managed env block between the cd line and the launch line.
        // find the launch line index (the one containing wine or "./" )
        let launch_idx = lines.iter().position(|l| {
            l.contains("wine ") || l.starts_with("\"./")
        }).unwrap_or(lines.len());

        let env_block = generate_env_block(opts, is_windows, wine_prefix);
        let mut block_with_markers = vec![ENV_BLOCK_START.to_string()];
        block_with_markers.extend(env_block);
        block_with_markers.push(ENV_BLOCK_END.to_string());
        block_with_markers.push(String::new()); // blank line separator

        for (i, line) in block_with_markers.into_iter().enumerate() {
            lines.insert(launch_idx + i, line);
        }

        let content = lines.join("\n") + "\n";
        fs::write(&script_path, content)?;
        ScriptGenerationResult::Generated
    };

    // Ensure script is executable
    let mut perms = fs::metadata(&script_path)?.permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&script_path, perms)?;

    Ok((script_path, result))
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

    #[test]
    fn test_fresh_generation_has_markers_and_env() {
        let dir = tempfile::tempdir().unwrap();
        let game_dir = dir.path();
        let binary = Path::new("game.exe");
        let opts = WineOpts {
            sdl_driver: Some("x11".to_string()),
            dxvk_hud: Some("fps".to_string()),
            ..Default::default()
        };

        let (path, result) = create_launcher_script(
            game_dir, binary, "Test Game", true, None, Some(&opts),
        ).unwrap();

        assert_eq!(result, ScriptGenerationResult::Generated);
        let content = fs::read_to_string(&path).unwrap();

        // Both markers present exactly once
        assert_eq!(content.matches(ENV_BLOCK_START).count(), 1);
        assert_eq!(content.matches(ENV_BLOCK_END).count(), 1);

        // Env exports inside the markers
        let start_idx = content.find(ENV_BLOCK_START).unwrap();
        let end_idx = content.find(ENV_BLOCK_END).unwrap();
        let block = &content[start_idx..end_idx];
        assert!(block.contains("export SDL_VIDEODRIVER=\"x11\""));
        assert!(block.contains("export DXVK_HUD=\"fps\""));
    }

    #[test]
    fn test_patch_changes_env_preserves_outside() {
        let dir = tempfile::tempdir().unwrap();
        let game_dir = dir.path();
        let binary = Path::new("game.exe");

        // Generate initial script with sdl_driver=x11
        let opts1 = WineOpts {
            sdl_driver: Some("x11".to_string()),
            ..Default::default()
        };
        let (path, _) = create_launcher_script(
            game_dir, binary, "Test Game", true, None, Some(&opts1),
        ).unwrap();

        // Add a user-added line after the end marker (simulating manual edit outside markers)
        let mut content = fs::read_to_string(&path).unwrap();
        content.push_str("echo 'user custom line'\n");
        fs::write(&path, &content).unwrap();

        // Patch with different opts
        let opts2 = WineOpts {
            sdl_driver: Some("wayland".to_string()),
            dxvk_hud: Some("full".to_string()),
            ..Default::default()
        };
        let (_, result) = create_launcher_script(
            game_dir, binary, "Test Game", true, None, Some(&opts2),
        ).unwrap();

        assert_eq!(result, ScriptGenerationResult::Patched);

        let new_content = fs::read_to_string(&path).unwrap();

        // User-added line outside markers is preserved
        assert!(new_content.contains("echo 'user custom line'"));

        // Env block was updated
        let start_idx = new_content.find(ENV_BLOCK_START).unwrap();
        let end_idx = new_content.find(ENV_BLOCK_END).unwrap();
        let block = &new_content[start_idx..end_idx];
        assert!(block.contains("export SDL_VIDEODRIVER=\"wayland\""));
        assert!(block.contains("export DXVK_HUD=\"full\""));
        // Old value gone
        assert!(!block.contains("export SDL_VIDEODRIVER=\"x11\""));
    }

    #[test]
    fn test_missing_end_marker_returns_skipped() {
        let dir = tempfile::tempdir().unwrap();
        let game_dir = dir.path();
        let script_path = game_dir.join("start_game.sh");

        // Write a file with only the start marker (corrupt)
        let corrupt_content = format!(
            "#!/usr/bin/env bash\nset -e\n{}\necho hello\n",
            ENV_BLOCK_START
        );
        fs::write(&script_path, &corrupt_content).unwrap();
        let original_bytes = fs::read(&script_path).unwrap();

        let opts = WineOpts::default();
        let (_, result) = create_launcher_script(
            game_dir, Path::new("game.exe"), "Test Game", false, None, Some(&opts),
        ).unwrap();

        assert_eq!(result, ScriptGenerationResult::SkippedCorruptMarkers);

        // File is byte-identical to before
        let after_bytes = fs::read(&script_path).unwrap();
        assert_eq!(original_bytes, after_bytes);
    }

    #[test]
    fn test_no_exec_prefix_in_generated_script() {
        let dir = tempfile::tempdir().unwrap();
        let game_dir = dir.path();

        // Test with keyd enabled (previously would have used exec prefix)
        let opts = WineOpts {
            keyd_remap: Some("leftshift=leftcontrol".to_string()),
            ..Default::default()
        };
        let (path, _) = create_launcher_script(
            game_dir, Path::new("./mygame"), "My Game", false, None, Some(&opts),
        ).unwrap();

        let content = fs::read_to_string(&path).unwrap();
        // The launch line should NOT start with "exec "
        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("\"./") || trimmed.starts_with("wine ") {
                assert!(!trimmed.starts_with("exec "),
                    "Launch line should not have exec prefix: {}", trimmed);
            }
        }

        // Also test without keyd
        let dir2 = tempfile::tempdir().unwrap();
        let (path2, _) = create_launcher_script(
            dir2.path(), Path::new("./mygame"), "My Game", false, None, None,
        ).unwrap();
        let content2 = fs::read_to_string(&path2).unwrap();
        for line in content2.lines() {
            let trimmed = line.trim();
            if trimmed.starts_with("\"./") || trimmed.starts_with("wine ") {
                assert!(!trimmed.starts_with("exec "),
                    "Launch line should not have exec prefix: {}", trimmed);
            }
        }
    }

    #[test]
    fn test_markers_present_even_with_empty_env_block() {
        let dir = tempfile::tempdir().unwrap();
        let game_dir = dir.path();

        // Default opts: no keyd, no sdl_driver, not windows → empty env block
        let default_opts = WineOpts::default();
        let (path, result) = create_launcher_script(
            game_dir, Path::new("./start"), "Test Game", false, None, Some(&default_opts),
        ).unwrap();
        assert_eq!(result, ScriptGenerationResult::Generated);

        let content = fs::read_to_string(&path).unwrap();

        // Markers must be present even though block content is empty
        assert_eq!(content.matches(ENV_BLOCK_START).count(), 1,
            "START marker missing on fresh generation with empty env block");
        assert_eq!(content.matches(ENV_BLOCK_END).count(), 1,
            "END marker missing on fresh generation with empty env block");

        // Now patch with a real setting — must succeed, not SkippedCorruptMarkers
        let patched_opts = WineOpts {
            sdl_driver: Some("wayland".to_string()),
            ..Default::default()
        };
        let (_, patch_result) = create_launcher_script(
            game_dir, Path::new("./start"), "Test Game", false, None, Some(&patched_opts),
        ).unwrap();
        assert_eq!(patch_result, ScriptGenerationResult::Patched,
            "Patching an empty-but-present marker block should succeed");

        let patched = fs::read_to_string(&path).unwrap();
        assert!(patched.contains("export SDL_VIDEODRIVER=\"wayland\""),
            "Patched content should contain the SDL driver export");
    }
}

