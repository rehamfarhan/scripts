mod config;
mod db;
mod launcher;
mod model;
mod recap;
mod scanner;
mod ui;

use fuzzy_matcher::skim::SkimMatcherV2;
use fuzzy_matcher::FuzzyMatcher;
use std::path::PathBuf;

use crate::config::resolve_games_dir;
use crate::db::Database;
use crate::launcher::launch_game_attached;

fn main() -> std::io::Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut games_dir: Option<PathBuf> = None;
    let mut query: Option<String> = None;

    let mut i = 0;
    while i < args.len() {
        if args[i] == "-v" || args[i] == "--version" {
            println!("run v{}", env!("CARGO_PKG_VERSION"));
            return Ok(());
        } else if args[i] == "-h" || args[i] == "--help" {
            println!("run v{} - Fast TUI game launcher & session tracker", env!("CARGO_PKG_VERSION"));
            println!("\nUsage:\n  run [OPTIONS] [GAME_NAME]\n\nOptions:\n  -v, --version           Print version\n  -h, --help              Print help\n      --games-dir <PATH>  Specify custom games directory\n\nArguments:\n  [GAME_NAME]             Direct quick-launch by fuzzy name");
            return Ok(());
        } else if args[i] == "--games-dir" && i + 1 < args.len() {
            games_dir = Some(PathBuf::from(&args[i + 1]));
            i += 2;
        } else if !args[i].starts_with('-') && query.is_none() {
            query = Some(args[i].clone());
            i += 1;
        } else {
            i += 1;
        }
    }

    let games_root = resolve_games_dir(games_dir)?;

    // Quick-launch mode
    if let Some(ref q) = query {
        let db = Database::open(&games_root).expect("Failed to open SQLite database");
        let all_games = db.get_all_games().unwrap_or_default();
        let matcher = SkimMatcherV2::default();

        let mut best_match = None;
        let mut highest_score = -1000;

        for game in all_games {
            if game.ignored {
                continue;
            }

            let name_match = matcher.fuzzy_match(&game.display_name, q);
            let dir_match = matcher.fuzzy_match(&game.dir, q);
            let score = match (name_match, dir_match) {
                (Some(s1), Some(s2)) => s1.max(s2),
                (Some(s1), None) => s1,
                (None, Some(s2)) => s2,
                (None, None) => continue,
            };

            if score > highest_score {
                highest_score = score;
                best_match = Some(game);
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
