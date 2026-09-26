use crossterm::cursor::Show;
use crossterm::event::{self, Event};
use crossterm::execute;
use crossterm::terminal::{disable_raw_mode, enable_raw_mode, LeaveAlternateScreen};
use std::io::{stdout, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Instant;

use crate::db::{Database, GameRecord};
use crate::recap::render_post_game_recap;
use crate::scanner::create_launcher_script;

/// A launch shorter than this (seconds) is treated as a failure to start —
/// bad CWD, missing dependency, crash-on-start — and is NOT recorded as a
/// play session, so playtime / times-played stay honest. A long session that
/// ends in a crash still counts.
const MIN_SESSION_SECS: u64 = 10;

fn should_record_session(elapsed_sec: u64) -> bool {
    elapsed_sec >= MIN_SESSION_SECS
}

pub fn launch_game_attached(
    games_root: &Path,
    game: &GameRecord,
    wait_key_before_exit: bool,
) -> std::io::Result<()> {
    let folder_path = games_root.join(&game.dir);
    let binary_path = PathBuf::from(&game.binary);
    let wine_prefix = game.wine_prefix.as_ref().map(PathBuf::from);

    // Ensure launcher script is generated and up to date
    let (script_path, _gen_result) = create_launcher_script(
        &folder_path,
        &binary_path,
        &game.display_name,
        game.is_windows,
        wine_prefix.as_deref(),
        game.wine_opts.as_ref(),
    )?;

    // Leave TUI alternate screen, disable raw mode, show cursor
    let mut out = stdout();
    let _ = execute!(out, LeaveAlternateScreen, Show);
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
    let exit_status = child.wait()?;

    let elapsed_sec = start_time.elapsed().as_secs();

    // Ensure cursor is visible and terminal is clean
    let _ = execute!(stdout(), Show);
    let _ = disable_raw_mode();

    // Intentional redundant keyd cleanup — safety net for when the shell trap
    // in start_game.sh cannot fire (e.g. game killed with SIGKILL, shell already dead).
    // The shell trap handles normal exit; this handles abnormal exit. Do not remove.
    if let Some(ref opts) = game.wine_opts {
        if opts.keyd_remap.is_some() {
            let _ = Command::new("keyd")
                .arg("reload")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
        }
    }

    // Check for game crash or non-zero exit
    if !exit_status.success() {
        let code_str = exit_status
            .code()
            .map(|c| format!("code {}", c))
            .unwrap_or_else(|| "terminated by signal".to_string());
        println!("\n\x1b[33m⚠️ Game exited with {}\x1b[0m", code_str);
    }

    // Update playtime statistics in SQLite database — but only for a real
    // session. A launch that died before the floor (crash-on-start, bad CWD)
    // shouldn't inflate playtime or times-played.
    let (total_seconds, play_count, rating) = if !should_record_session(elapsed_sec) {
        (game.playtime_seconds, game.play_count, game.rating)
    } else if let Ok(db) = Database::open(games_root) {
        db.record_session(&game.dir, elapsed_sec, &iso_now)
            .unwrap_or((game.playtime_seconds + elapsed_sec, game.play_count + 1, game.rating))
    } else {
        (game.playtime_seconds + elapsed_sec, game.play_count + 1, game.rating)
    };

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

#[cfg(test)]
mod tests {
    use super::should_record_session;

    #[test]
    fn launch_shorter_than_floor_is_not_recorded() {
        assert!(!should_record_session(0));
        assert!(!should_record_session(9));
    }

    #[test]
    fn launch_at_floor_or_longer_is_recorded() {
        assert!(should_record_session(10));
        assert!(should_record_session(3600));
        // A 2-hour session that ends in a crash still counts.
        assert!(should_record_session(7200));
    }
}
