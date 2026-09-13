use std::path::PathBuf;

pub const REGISTRY_FILENAME: &str = ".run_registry.json";
pub const STATS_FILENAME: &str = ".run_stats.json";
pub const IGNORE_DIRS: &[&str] = &["lib", "lib64", "share", ".git", ".wine", "node_modules"];

pub fn default_games_dir() -> PathBuf {
    dirs::home_dir().map(|h| h.join("Games")).unwrap_or_else(|| PathBuf::from("Games"))
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
