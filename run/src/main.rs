mod config;
mod launcher;
mod model;
mod recap;
mod scanner;
mod ui;

use fuzzy_matcher::skim::SkimMatcherV2;
use fuzzy_matcher::FuzzyMatcher;
use std::path::PathBuf;

use crate::config::default_games_dir;
use crate::launcher::launch_game_attached;
use crate::model::GameRegistry;

fn main() -> std::io::Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut games_dir: Option<PathBuf> = None;
    let mut query: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        if args[i] == "--games-dir" && i + 1 < args.len() {
            games_dir = Some(PathBuf::from(&args[i + 1]));
            i += 2;
        } else if !args[i].starts_with('-') && query.is_none() {
            query = Some(args[i].clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    let games_root = games_dir
        .unwrap_or_else(default_games_dir)
        .canonicalize()
        .unwrap_or_else(|_| default_games_dir());

    let _ = std::fs::create_dir_all(&games_root);

    // Quick-launch mode
    if let Some(ref q) = query {
        let registry = GameRegistry::load(&games_root);
        let matcher = SkimMatcherV2::default();

        let mut best_match = None;
        let mut highest_score = -1000;

        for game in registry.games.values() {
            if game.ignored.unwrap_or(false) {
                continue;
            }

            let name_match = matcher.fuzzy_match(&game.display_name, q).unwrap_or(0);
            let dir_match = matcher.fuzzy_match(&game.dir, q).unwrap_or(0);
            let score = name_match.max(dir_match);

            if score > highest_score {
                highest_score = score;
                best_match = Some(game.clone());
            }
        }

        if let Some(target_game) = best_match {
            println!("🚀 Quick-launching '{}'...", target_game.display_name);
            return launch_game_attached(&games_root, &target_game, false);
        } else {
            eprintln!("Error: No game matching '{}' found in library.", q);
            std::process::exit(1);
        }
    }

    // Launch Full Interactive TUI Dashboard
    ui::run_tui(games_root)
}
