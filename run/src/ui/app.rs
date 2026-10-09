use fuzzy_matcher::skim::SkimMatcherV2;
use fuzzy_matcher::FuzzyMatcher;
use std::path::PathBuf;
use std::time::Instant;

use crate::config::IGNORE_DIRS;
use crate::db::{Database, GameRecord};
use crate::model::WineOpts;
use crate::scanner::scan_executables;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SortField {
    Recent,
    Playtime,
    Rating,
    Alphabetical,
    Sessions,
}

impl SortField {
    pub fn next(self) -> Self {
        match self {
            Self::Recent => Self::Playtime,
            Self::Playtime => Self::Rating,
            Self::Rating => Self::Alphabetical,
            Self::Alphabetical => Self::Sessions,
            Self::Sessions => Self::Recent,
        }
    }

    #[allow(dead_code)]
    pub fn prev(self) -> Self {
        match self {
            Self::Recent => Self::Sessions,
            Self::Playtime => Self::Recent,
            Self::Rating => Self::Playtime,
            Self::Alphabetical => Self::Rating,
            Self::Sessions => Self::Alphabetical,
        }
    }

    #[allow(dead_code)]
    pub fn name(self) -> &'static str {
        match self {
            Self::Recent => "Recent ⏱️",
            Self::Playtime => "Playtime ⏳",
            Self::Rating => "Rating 🌟",
            Self::Alphabetical => "Alphabetical 🔤",
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
    ResetScriptConfirmation {
        game_name: String,
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
    pub sort_field: SortField,
    pub sort_descending: bool,
    pub active_modal: ActiveModal,
    pub toast: Option<(String, Instant)>,
    pub should_quit: bool,
    pub launch_target: Option<GameRecord>,
    pub show_quick_actions: bool,
    pub needs_editor: Option<PathBuf>,
    pub keyd_editor_file: Option<PathBuf>,
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
            is_searching: true, // Starts in fuzzy search mode by default!
            show_quick_actions: false, // Hidden by default, toggled with 'i'
            sort_field: SortField::Recent,
            sort_descending: true, // Default descending order (e.g. most recent, highest playtime/rating)
            active_modal: ActiveModal::None,
            toast: None,
            should_quit: false,
            launch_target: None,
            needs_editor: None,
            keyd_editor_file: None,
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

    pub fn sort_label(&self) -> String {
        let arrow = if self.sort_descending { "▼" } else { "▲" };
        match self.sort_field {
            SortField::Recent => {
                if self.sort_descending {
                    "Recent ⏱️ ▼".to_string()
                } else {
                    "Oldest ⏱️ ▲".to_string()
                }
            }
            SortField::Playtime => format!("Playtime ⏳ {}", arrow),
            SortField::Rating => format!("Rating 🌟 {}", arrow),
            SortField::Alphabetical => {
                if self.sort_descending {
                    "Z-A 🔤 ▼".to_string()
                } else {
                    "A-Z 🔤 ▲".to_string()
                }
            }
            SortField::Sessions => format!("Sessions 🎮 {}", arrow),
        }
    }

    pub fn reload_games(&mut self) {
        let mut list: Vec<GameRecord> = self
            .db
            .get_all_games()
            .unwrap_or_default()
            .into_iter()
            .filter(|g| !g.ignored)
            .collect();

        // Sort based on active sort_field and sort_descending, with favorites pinned on top
        list.sort_by(|a, b| {
            if a.favorite != b.favorite {
                return b.favorite.cmp(&a.favorite);
            }

            let cmp = match self.sort_field {
                SortField::Recent => {
                    let lp_a = a.last_played.as_deref().unwrap_or("");
                    let lp_b = b.last_played.as_deref().unwrap_or("");
                    lp_a.cmp(lp_b)
                }
                SortField::Playtime => a.playtime_seconds.cmp(&b.playtime_seconds),
                SortField::Rating => a.rating.cmp(&b.rating),
                SortField::Alphabetical => {
                    a.display_name.to_lowercase().cmp(&b.display_name.to_lowercase())
                }
                SortField::Sessions => a.play_count.cmp(&b.play_count),
            };

            let ordered_cmp = if self.sort_descending {
                cmp.reverse()
            } else {
                cmp
            };

            ordered_cmp.then_with(|| a.display_name.cmp(&b.display_name))
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

    pub fn select_first(&mut self) {
        if !self.filtered_indices.is_empty() {
            self.selected_index = 0;
        }
    }

    pub fn select_last(&mut self) {
        if !self.filtered_indices.is_empty() {
            self.selected_index = self.filtered_indices.len().saturating_sub(1);
        }
    }

    pub fn scroll_down(&mut self, count: usize) {
        if !self.filtered_indices.is_empty() {
            self.selected_index = (self.selected_index + count).min(self.filtered_indices.len() - 1);
        }
    }

    pub fn scroll_up(&mut self, count: usize) {
        if !self.filtered_indices.is_empty() {
            self.selected_index = self.selected_index.saturating_sub(count);
        }
    }

    pub fn check_unregistered_folders(&mut self) {
        // Include hidden dirs so a hidden game's folder doesn't re-trigger the wizard
        let existing_dirs: std::collections::HashSet<String> = self
            .db
            .get_all_dir_keys()
            .unwrap_or_default()
            .into_iter()
            .map(|d| d.to_lowercase())
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
