use fuzzy_matcher::skim::SkimMatcherV2;
use fuzzy_matcher::FuzzyMatcher;
use std::path::PathBuf;
use std::time::Instant;

use crate::config::IGNORE_DIRS;
use crate::db::{Database, GameRecord};
use crate::model::WineOpts;
use crate::scanner::scan_executables;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortMode {
    Recent,
    Playtime,
    Rating,
    AlphabeticalAsc,
    AlphabeticalDesc,
    Sessions,
}

impl SortMode {
    pub fn next(self) -> Self {
        match self {
            Self::Recent => Self::Playtime,
            Self::Playtime => Self::Rating,
            Self::Rating => Self::AlphabeticalAsc,
            Self::AlphabeticalAsc => Self::AlphabeticalDesc,
            Self::AlphabeticalDesc => Self::Sessions,
            Self::Sessions => Self::Recent,
        }
    }

    pub fn prev(self) -> Self {
        match self {
            Self::Recent => Self::Sessions,
            Self::Playtime => Self::Recent,
            Self::Rating => Self::Playtime,
            Self::AlphabeticalAsc => Self::Rating,
            Self::AlphabeticalDesc => Self::AlphabeticalAsc,
            Self::Sessions => Self::AlphabeticalDesc,
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Self::Recent => "Recent ⏱️",
            Self::Playtime => "Playtime ⏳",
            Self::Rating => "Rating 🌟",
            Self::AlphabeticalAsc => "A-Z 🔤",
            Self::AlphabeticalDesc => "Z-A 🔤",
            Self::Sessions => "Sessions 🎮",
        }
    }
}

#[derive(Debug, Clone)]
pub enum ActiveModal {
    None,
    RateGame {
        selected_opt: usize, // 0..=10 (representing ratings 10 down to 0)
    },
    KeyboardPatch {
        selected_opt: usize,
        custom_input: String,
        is_custom_mode: bool,
    },
    ExecutionSettings {
        selected_opt: usize,
        is_windows: bool,
        opts: WineOpts,
    },
    ChangeBinary {
        binaries: Vec<PathBuf>,
        filtered_indices: Vec<usize>,
        selected_bin: usize,
        search_query: String,
    },
    RenameGame {
        input: String,
    },
    NewGameWizard {
        folders: Vec<PathBuf>,
        current_idx: usize,
        binaries: Vec<PathBuf>,
        filtered_indices: Vec<usize>,
        selected_bin: usize,
        search_query: String,
        is_searching: bool, // Default true; Esc toggles to selection mode
    },
}

pub struct App {
    pub games_root: PathBuf,
    pub db: Database,
    pub all_games: Vec<GameRecord>,
    pub filtered_indices: Vec<usize>,
    pub selected_index: usize,
    pub search_query: String,
    pub is_searching: bool,
    pub sort_mode: SortMode,
    pub active_modal: ActiveModal,
    pub toast: Option<(String, Instant)>,
    pub should_quit: bool,
    pub launch_target: Option<GameRecord>,
    pub needs_editor: Option<PathBuf>,
    matcher: SkimMatcherV2,
}

impl App {
    pub fn new(games_root: PathBuf) -> Self {
        let db = Database::open(&games_root).expect("Failed to open SQLite database");

        let mut app = Self {
            games_root,
            db,
            all_games: Vec::new(),
            filtered_indices: Vec::new(),
            selected_index: 0,
            search_query: String::new(),
            is_searching: false,
            sort_mode: SortMode::Recent,
            active_modal: ActiveModal::None,
            toast: None,
            should_quit: false,
            launch_target: None,
            needs_editor: None,
            matcher: SkimMatcherV2::default(),
        };

        app.reload_games();
        app.check_unregistered_folders();
        app
    }

    pub fn set_toast(&mut self, msg: impl Into<String>) {
        self.toast = Some((msg.into(), Instant::now()));
    }

    pub fn toast_text(&self) -> Option<&str> {
        if let Some((ref msg, time)) = self.toast {
            if time.elapsed().as_secs() < 4 {
                return Some(msg.as_str());
            }
        }
        None
    }

    pub fn reload_games(&mut self) {
        let mut list: Vec<GameRecord> = self
            .db
            .get_all_games()
            .unwrap_or_default()
            .into_iter()
            .filter(|g| !g.ignored)
            .collect();

        // Sort based on active sort_mode, with favorites pinned on top
        list.sort_by(|a, b| {
            if a.favorite != b.favorite {
                return b.favorite.cmp(&a.favorite);
            }

            match self.sort_mode {
                SortMode::Recent => {
                    let lp_a = a.last_played.as_deref().unwrap_or("");
                    let lp_b = b.last_played.as_deref().unwrap_or("");
                    lp_b.cmp(lp_a).then_with(|| a.display_name.cmp(&b.display_name))
                }
                SortMode::Playtime => {
                    b.playtime_seconds.cmp(&a.playtime_seconds)
                        .then_with(|| a.display_name.cmp(&b.display_name))
                }
                SortMode::Rating => {
                    b.rating.cmp(&a.rating)
                        .then_with(|| a.display_name.cmp(&b.display_name))
                }
                SortMode::AlphabeticalAsc => {
                    a.display_name.to_lowercase().cmp(&b.display_name.to_lowercase())
                }
                SortMode::AlphabeticalDesc => {
                    b.display_name.to_lowercase().cmp(&a.display_name.to_lowercase())
                }
                SortMode::Sessions => {
                    b.play_count.cmp(&a.play_count)
                        .then_with(|| a.display_name.cmp(&b.display_name))
                }
            }
        });

        self.all_games = list;
        self.apply_filter();
    }

    pub fn apply_filter(&mut self) {
        if self.search_query.is_empty() {
            self.filtered_indices = (0..self.all_games.len()).collect();
        } else {
            let mut matches = Vec::new();
            for (idx, g) in self.all_games.iter().enumerate() {
                let text = format!("{} {}", g.display_name, g.dir);
                if let Some(score) = self.matcher.fuzzy_match(&text, &self.search_query) {
                    matches.push((idx, score, g.favorite));
                }
            }
            // Favorites pinned, then score descending
            matches.sort_by(|a, b| b.2.cmp(&a.2).then_with(|| b.1.cmp(&a.1)));
            self.filtered_indices = matches.into_iter().map(|(idx, _, _)| idx).collect();
        }

        if self.selected_index >= self.filtered_indices.len() && !self.filtered_indices.is_empty() {
            self.selected_index = self.filtered_indices.len() - 1;
        }
    }

    pub fn selected_game(&self) -> Option<&GameRecord> {
        self.filtered_indices
            .get(self.selected_index)
            .and_then(|&idx| self.all_games.get(idx))
    }

    pub fn select_next(&mut self) {
        if !self.filtered_indices.is_empty() {
            self.selected_index = (self.selected_index + 1) % self.filtered_indices.len();
        }
    }

    pub fn select_prev(&mut self) {
        if !self.filtered_indices.is_empty() {
            if self.selected_index == 0 {
                self.selected_index = self.filtered_indices.len() - 1;
            } else {
                self.selected_index -= 1;
            }
        }
    }

    pub fn check_unregistered_folders(&mut self) {
        let existing_dirs: std::collections::HashSet<String> = self
            .db
            .get_all_games()
            .unwrap_or_default()
            .into_iter()
            .map(|g| g.dir.to_lowercase())
            .collect();

        let mut unregistered = Vec::new();
        if let Ok(entries) = std::fs::read_dir(&self.games_root) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    let name = entry.file_name().to_string_lossy().to_string();
                    if !name.starts_with('.')
                        && !IGNORE_DIRS.contains(&name.as_str())
                        && !existing_dirs.contains(&name.to_lowercase())
                    {
                        unregistered.push(path);
                    }
                }
            }
        }

        unregistered.sort();

        if !unregistered.is_empty() {
            let first_folder = &unregistered[0];
            let binaries = scan_executables(first_folder, 2);
            let filtered_indices: Vec<usize> = (0..binaries.len()).collect();

            self.active_modal = ActiveModal::NewGameWizard {
                folders: unregistered,
                current_idx: 0,
                binaries,
                filtered_indices,
                selected_bin: 0,
                search_query: String::new(),
                is_searching: true, // Default to search mode as requested!
            };
        }
    }
}
