use crossterm::event::{self, Event};
use crossterm::terminal::{disable_raw_mode, enable_raw_mode, LeaveAlternateScreen};
use crossterm::execute;
use std::io::{stdout, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Instant;

use crate::model::{GameEntry, GameStats};
use crate::recap::render_post_game_recap;
use crate::scanner::create_launcher_script;

pub fn launch_game_attached(
    games_root: &Path,
    game: &GameEntry,
    wait_key_before_exit: bool,
) -> std::io::Result<()> {
    let folder_path = games_root.join(&game.dir);
    let binary_path = PathBuf::from(&game.binary);
    let wine_prefix = game.wine_prefix.as_ref().map(PathBuf::from);

    // Ensure launcher script is generated and up to date
    let script_path = create_launcher_script(
        &folder_path,
        &binary_path,
        &game.display_name,
        game.is_windows,
        wine_prefix.as_deref(),
        game.wine_opts.as_ref(),
    )?;

    // Leave TUI alternate screen and disable raw mode
    let mut out = stdout();
    let _ = execute!(out, LeaveAlternateScreen);
    let _ = disable_raw_mode();
    print!("\x1b[H\x1b[2J");
    let _ = out.flush();

    println!("\x1b[1m🚀 Launching '{}'...\x1b[0m\n", game.display_name);

    let start_time = Instant::now();
    let iso_now = chrono::Utc::now().to_rfc3339();

    // Sanitize environment variables
    let mut cmd = Command::new(&script_path);
    cmd.current_dir(&folder_path)
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

    if let Ok(sdl_drv) = std::env::var("SDL_VIDEODRIVER") {
        if sdl_drv.contains(',') {
            cmd.env_remove("SDL_VIDEODRIVER");
        }
    }
    if let Ok(sdl_drv) = std::env::var("SDL_VIDEO_DRIVER") {
        if sdl_drv.contains(',') {
            cmd.env_remove("SDL_VIDEO_DRIVER");
        }
    }

    // Spawn and wait for game process
    let mut child = cmd.spawn()?;
    let _ = child.wait();

    let elapsed_sec = start_time.elapsed().as_secs();

    // Keyd safety cleanup
    if let Some(ref opts) = game.wine_opts {
        if opts.keyd_remap.is_some() {
            let _ = Command::new("keyd")
                .arg("reload")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
    }

    // Update playtime statistics
    let mut stats_data = GameStats::load(games_root);
    let (total_seconds, play_count, rating) = {
        let entry = stats_data.stats.entry(game.dir.clone()).or_default();
        entry.playtime_seconds += elapsed_sec;
        entry.play_count += 1;
        entry.last_played = Some(iso_now);
        (entry.playtime_seconds, entry.play_count, entry.rating)
    };
    let _ = stats_data.save(games_root);

    // Render post-game recap card
    render_post_game_recap(
        &game.display_name,
        elapsed_sec,
        total_seconds,
        play_count,
        rating,
        game.is_windows,
    );

    if wait_key_before_exit {
        println!("\n  \x1b[90m[Press any key to return to launcher...]\x1b[0m");
        let _ = enable_raw_mode();
        loop {
            if let Ok(Event::Key(key_event)) = event::read() {
                if key_event.kind == crossterm::event::KeyEventKind::Press {
                    break;
                }
            }
        }
        let _ = disable_raw_mode();
    }

    Ok(())
}
