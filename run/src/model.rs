use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::BufReader;
use std::path::Path;

use crate::config::{REGISTRY_FILENAME, STATS_FILENAME};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WineOpts {
    pub resolution: Option<String>,
    pub dxvk_hud: Option<String>,
    pub win_ver: Option<String>,
    pub sdl_driver: Option<String>,
    pub keyd_remap: Option<String>,
}

impl Default for WineOpts {
    fn default() -> Self {
        Self {
            resolution: None,
            dxvk_hud: None,
            win_ver: Some("win10".to_string()),
            sdl_driver: None,
            keyd_remap: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameEntry {
    pub dir: String,
    pub display_name: String,
    pub binary: String,
    pub is_windows: bool,
    pub wine_prefix: Option<String>,
    #[serde(default)]
    pub wine_opts: Option<WineOpts>,
    pub icon: Option<String>,
    pub launcher_script: Option<String>,
    pub desktop_entry: Option<String>,
    #[serde(default)]
    pub ignored: Option<bool>,
    #[serde(default)]
    pub custom_wrapper: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameRegistry {
    pub version: u32,
    pub games: HashMap<String, GameEntry>,
}

impl Default for GameRegistry {
    fn default() -> Self {
        Self {
            version: 1,
            games: HashMap::new(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameStatEntry {
    #[serde(default)]
    pub rating: u8,
    #[serde(default)]
    pub playtime_seconds: u64,
    #[serde(default)]
    pub play_count: u64,
    pub last_played: Option<String>,
}

impl Default for GameStatEntry {
    fn default() -> Self {
        Self {
            rating: 0,
            playtime_seconds: 0,
            play_count: 0,
            last_played: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GameStats {
    pub version: u32,
    pub stats: HashMap<String, GameStatEntry>,
}

impl Default for GameStats {
    fn default() -> Self {
        Self {
            version: 1,
            stats: HashMap::new(),
        }
    }
}

impl GameRegistry {
    pub fn load(games_root: &Path) -> Self {
        let reg_path = games_root.join(REGISTRY_FILENAME);
        if reg_path.is_file() {
            if let Ok(file) = File::open(&reg_path) {
                let reader = BufReader::new(file);
                if let Ok(registry) = serde_json::from_reader(reader) {
                    return registry;
                }
            }
        }
        Self::default()
    }

    #[allow(dead_code)]
    pub fn save(&self, games_root: &Path) -> std::io::Result<()> {
        let reg_path = games_root.join(REGISTRY_FILENAME);
        let tmp_path = games_root.join(format!("{}.tmp", REGISTRY_FILENAME));
        let json_bytes = serde_json::to_vec_pretty(self)?;
        fs::write(&tmp_path, json_bytes)?;
        fs::rename(tmp_path, reg_path)?;
        Ok(())
    }
}

impl GameStats {
    pub fn load(games_root: &Path) -> Self {
        let stats_path = games_root.join(STATS_FILENAME);
        if stats_path.is_file() {
            if let Ok(file) = File::open(&stats_path) {
                let reader = BufReader::new(file);
                if let Ok(stats) = serde_json::from_reader(reader) {
                    return stats;
                }
            }
        }
        Self::default()
    }

    pub fn get_stat(&self, dir_key: &str) -> Option<&GameStatEntry> {
        if let Some(entry) = self.stats.get(dir_key) {
            return Some(entry);
        }
        let lower = dir_key.to_lowercase();
        self.stats.iter().find_map(|(k, v)| {
            if k.to_lowercase() == lower {
                Some(v)
            } else {
                None
            }
        })
    }

    #[allow(dead_code)]
    pub fn get_stat_mut(&mut self, dir_key: &str) -> &mut GameStatEntry {
        if self.stats.contains_key(dir_key) {
            return self.stats.get_mut(dir_key).unwrap();
        }
        let lower = dir_key.to_lowercase();
        let existing_key = self
            .stats
            .keys()
            .find(|k| k.to_lowercase() == lower)
            .cloned();

        if let Some(key) = existing_key {
            self.stats.get_mut(&key).unwrap()
        } else {
            self.stats.entry(dir_key.to_string()).or_default()
        }
    }

    #[allow(dead_code)]
    pub fn save(&self, games_root: &Path) -> std::io::Result<()> {
        let stats_path = games_root.join(STATS_FILENAME);
        let tmp_path = games_root.join(format!("{}.tmp", STATS_FILENAME));
        let json_bytes = serde_json::to_vec_pretty(self)?;
        fs::write(&tmp_path, json_bytes)?;
        fs::rename(tmp_path, stats_path)?;
        Ok(())
    }
}

// Helpers for formatting playtime & timestamps
pub fn format_playtime(seconds: u64) -> String {
    if seconds == 0 {
        return "0m".to_string();
    }
    if seconds < 3600 {
        let mins = seconds / 60;
        return format!("{}m", mins);
    }
    let hours = (seconds as f64) / 3600.0;
    format!("{:.1}h", hours)
}

pub fn format_relative_time(iso_str: Option<&str>) -> String {
    let Some(iso) = iso_str else {
        return "never".to_string();
    };
    match chrono::DateTime::parse_from_rfc3339(iso) {
        Ok(dt) => {
            let utc_dt = dt.with_timezone(&chrono::Utc);
            let now = chrono::Utc::now();
            let duration = now.signed_duration_since(utc_dt);
            let secs = duration.num_seconds();
            if secs < 60 {
                "just now".to_string()
            } else if secs < 3600 {
                format!("{}m ago", duration.num_minutes())
            } else if secs < 86400 {
                format!("{}h ago", duration.num_hours())
            } else if duration.num_days() == 1 {
                "yesterday".to_string()
            } else if duration.num_days() < 30 {
                format!("{}d ago", duration.num_days())
            } else {
                utc_dt.format("%b %d, %Y").to_string()
            }
        }
        Err(_) => "recently".to_string(),
    }
}

pub fn format_star_rating(rating: u8) -> String {
    let r = rating.min(10);
    if r == 0 {
        return "⚫⚫⚫⚫⚫  (0/10 • Unrated)".to_string();
    }

    let mut slots = String::new();
    for i in 0..5 {
        let threshold = (i + 1) * 2;
        if r >= threshold {
            slots.push_str("🌟");
        } else if r == threshold - 1 {
            slots.push_str("⭐️");
        } else {
            slots.push_str("⚫");
        }
    }

    let label = match r {
        10 => "Masterpiece",
        9 => "Exceptional",
        8 => "Great",
        7 => "Very Good",
        6 => "Good",
        5 => "Decent",
        4 => "Mediocre",
        3 => "Poor",
        2 => "Bad",
        1 => "Terrible",
        _ => "Unrated",
    };

    format!("{}  ({}/10 • {})", slots, r, label)
}
