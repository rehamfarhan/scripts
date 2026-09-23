use std::path::PathBuf;

pub const REGISTRY_FILENAME: &str = ".run_registry.json";
pub const STATS_FILENAME: &str = ".run_stats.json";
pub const IGNORE_DIRS: &[&str] = &["lib", "lib64", "share", ".git", ".wine", "node_modules"];

pub fn default_games_dir() -> PathBuf {
    dirs::home_dir().map(|h| h.join("Games")).unwrap_or_else(|| PathBuf::from("Games"))
}

/// Resolve the games root directory and ensure it exists.
///
/// The requested path (custom `--games-dir` value or the default) is created
/// if needed *before* canonicalization, so a not-yet-existing custom path is
/// never silently swapped for the default. Falls back to the (now created)
/// requested path only if canonicalization itself fails.
pub fn resolve_games_dir(requested: Option<PathBuf>) -> std::io::Result<PathBuf> {
    let path = requested.unwrap_or_else(default_games_dir);
    std::fs::create_dir_all(&path)?;
    Ok(path.canonicalize().unwrap_or(path))
}

pub fn desktop_dir() -> PathBuf {
    dirs::data_local_dir()
        .map(|d| d.join("applications"))
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".local/share/applications"))
}

pub fn user_name() -> String {
    std::env::var("USER")
        .unwrap_or_else(|_| "DirectPass".to_string())
        .trim()
        .to_string()
}

pub fn main_title() -> String {
    let name = user_name();
    let title_name = if !name.is_empty() {
        let mut c = name.chars();
        match c.next() {
            None => String::new(),
            Some(f) => f.to_uppercase().collect::<String>() + c.as_str(),
        }
    } else {
        "DirectPass".to_string()
    };
    format!("🏰 {}'s Game Dungeon 🎮", title_name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_games_dir_creates_missing_custom_path() {
        let temp = tempfile::tempdir().unwrap();
        let missing = temp.path().join("custom/games/not/created/yet");

        let resolved = resolve_games_dir(Some(missing.clone())).unwrap();

        assert!(resolved.is_dir(), "resolved path must exist after resolve");
        assert!(missing.is_dir(), "requested path must have been created");
    }

    #[test]
    fn resolve_games_dir_never_silently_swaps_custom_path_for_default() {
        let temp = tempfile::tempdir().unwrap();
        let missing = temp.path().join("custom_games");

        let resolved = resolve_games_dir(Some(missing.clone())).unwrap();

        // The bug: a non-existent custom --games-dir used to fall back to the
        // default ~/Games. The resolved root must stay under the requested path.
        let canonical_temp = temp.path().canonicalize().unwrap();
        assert!(
            resolved.starts_with(&canonical_temp),
            "resolved {:?} should live under requested {:?}",
            resolved,
            canonical_temp
        );
        assert_ne!(
            resolved,
            default_games_dir().canonicalize().unwrap_or(default_games_dir())
        );
    }
}
