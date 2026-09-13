use fuzzy_matcher::skim::SkimMatcherV2;
use fuzzy_matcher::FuzzyMatcher;
use std::path::PathBuf;
use std::time::Instant;

use crate::config::IGNORE_DIRS;
use crate::model::{GameEntry, GameRegistry, GameStats, WineOpts};
use crate::scanner::scan_executables;

#[derive(Debug, Clone, PartialEq)]
pub enum WizardStep {
    SelectBinary,
    NameGame,
    ConfigureSettings,
}

#[derive(Debug, Clone)]
pub enum ActiveModal {
    None,
    RateGame {
        selected_opt: usize,
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
        selected_bin: usize,
        display_name: String,
        step: WizardStep,
        opts: WineOpts,
    },
}

pub struct App {
    pub games_root: PathBuf,
    pub registry: GameRegistry,
    pub stats: GameStats,
    pub all_games: Vec<GameEntry>,
    pub filtered_indices: Vec<usize>,
    pub selected_index: usize,
    pub search_query: String,
    pub is_searching: bool,
    pub active_modal: ActiveModal,
    pub toast: Option<(String, Instant)>,
    pub should_quit: bool,
    pub launch_target: Option<GameEntry>,
    matcher: SkimMatcherV2,
}

impl App {
    pub fn new(games_root: PathBuf) -> Self {
        let registry = GameRegistry::load(&games_root);
        let stats = GameStats::load(&games_root);

        let mut app = Self {
            games_root,
            registry,
            stats,
            all_games: Vec::new(),
            filtered_indices: Vec::new(),
            selected_index: 0,
            search_query: String::new(),
            is_searching: false,
            active_modal: ActiveModal::None,
            toast: None,
            should_quit: false,
            launch_target: None,
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
        let mut list: Vec<GameEntry> = self
            .registry
            .games
            .values()
            .filter(|g| !g.ignored.unwrap_or(false))
            .cloned()
            .collect();

        // Sort by last played descending (with case-insensitive backwards-compatible stats lookup!)
        let stats = &self.stats;
        list.sort_by(|a, b| {
            let lp_a = stats.get_stat(&a.dir).and_then(|s| s.last_played.as_deref()).unwrap_or("");
            let lp_b = stats.get_stat(&b.dir).and_then(|s| s.last_played.as_deref()).unwrap_or("");
            lp_b.cmp(lp_a)
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
                    matches.push((idx, score));
                }
            }
            matches.sort_by(|a, b| b.1.cmp(&a.1));
            self.filtered_indices = matches.into_iter().map(|(idx, _)| idx).collect();
        }

        if self.selected_index >= self.filtered_indices.len() && !self.filtered_indices.is_empty() {
            self.selected_index = self.filtered_indices.len() - 1;
        }
    }

    pub fn selected_game(&self) -> Option<&GameEntry> {
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
        let mut unregistered = Vec::new();
        if let Ok(entries) = std::fs::read_dir(&self.games_root) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    let name = entry.file_name().to_string_lossy().to_string();
                    if !name.starts_with('.')
                        && !IGNORE_DIRS.contains(&name.as_str())
                        && !self.registry.games.contains_key(&name)
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
            let display_name = first_folder
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .replace(['_', '-'], " ");

            self.active_modal = ActiveModal::NewGameWizard {
                folders: unregistered,
                current_idx: 0,
                binaries,
                selected_bin: 0,
                display_name,
                step: WizardStep::SelectBinary,
                opts: WineOpts::default(),
            };
        }
    }
}
