mod downloader;
mod lyrics;
mod metadata;
mod presets;
mod ui;

use anyhow::Result;
use crossterm::{
    cursor::Show,
    event::{Event, KeyCode, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use downloader::{Downloader, DownloadProgress, DownloadSummary};
use metadata::MediaMetadata;
use presets::PresetType;
use ratatui::{backend::CrosstermBackend, Terminal};
use std::io::stdout;
use std::process::Command;
use std::time::Duration;
use tokio::sync::mpsc;
use ui::AppState;

fn get_clipboard_url() -> Option<String> {
    // Try wl-paste
    if let Ok(output) = Command::new("wl-paste").arg("-n").output() {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if text.starts_with("http://") || text.starts_with("https://") {
                return Some(text);
            }
        }
    }
    // Try xclip fallback
    if let Ok(output) = Command::new("xclip").args(["-selection", "clipboard", "-o"]).output() {
        if output.status.success() {
            let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if text.starts_with("http://") || text.starts_with("https://") {
                return Some(text);
            }
        }
    }
    None
}

fn send_desktop_notification(summary: &DownloadSummary) {
    let _ = Command::new("notify-send")
        .args([
            "-a",
            "MediaFetch",
            "-i",
            "video-x-generic",
            "Download Completed",
            &format!("{}\nSaved to {}", summary.title, summary.formatted_size),
        ])
        .spawn();
}

fn print_nerdy_summary(summary: &DownloadSummary) {
    println!();
    println!("\x1b[1;36m╭──────────────────────── 📥 MEDIAFETCH COMPLETE ────────────────────────╮\x1b[0m");
    println!("\x1b[1;36m│\x1b[0m  \x1b[1mTitle:\x1b[0m       \x1b[1;37m{:<57}\x1b[0m \x1b[1;36m│\x1b[0m", truncate_str(&summary.title, 57));
    println!("\x1b[1;36m│\x1b[0m  \x1b[1mCreator:\x1b[0m     \x1b[33m{:<57}\x1b[0m \x1b[1;36m│\x1b[0m", truncate_str(&summary.channel, 57));
    println!("\x1b[1;36m│\x1b[0m  \x1b[1mLocation:\x1b[0m    \x1b[34m{:<57}\x1b[0m \x1b[1;36m│\x1b[0m", truncate_str(&summary.file_path.to_string_lossy(), 57));
    println!("\x1b[1;36m│\x1b[0m  \x1b[1mFile Size:\x1b[0m   \x1b[32m{:<57}\x1b[0m \x1b[1;36m│\x1b[0m", truncate_str(&summary.formatted_size, 57));
    println!("\x1b[1;36m│\x1b[0m  \x1b[1mPreset:\x1b[0m      \x1b[35m{} ({})\x1b[0m", summary.preset.title(), summary.preset.badge());

    if let Some(ref lrc) = summary.lrc_path {
        println!("\x1b[1;36m│\x1b[0m  \x1b[1mLyrics:\x1b[0m      \x1b[1;32m✓ USLT embedded & .lrc companion created ({})\x1b[0m", lrc.file_name().unwrap_or_default().to_string_lossy());
    } else if summary.preset.should_fetch_lyrics() {
        println!("\x1b[1;36m│\x1b[0m  \x1b[1mLyrics:\x1b[0m      \x1b[90m✗ No online lyrics found on LRCLIB\x1b[0m");
    }

    println!("\x1b[1;36m│\x1b[0m  \x1b[1mElapsed:\x1b[0m     \x1b[36m{:.2}s\x1b[0m", summary.duration.as_secs_f64());
    println!("\x1b[1;36m╰────────────────────────────────────────────────────────────────────────╯\x1b[0m");
    println!();
}

fn truncate_str(s: &str, max_len: usize) -> String {
    if s.chars().count() > max_len {
        let truncated: String = s.chars().take(max_len.saturating_sub(3)).collect();
        format!("{}...", truncated)
    } else {
        s.to_string()
    }
}

fn print_help() {
    println!("\x1b[1;36mMediaFetch (Rust + Ratatui Edition)\x1b[0m");
    println!("A blazing-fast, beautiful TUI wrapper for yt-dlp with smart presets & LRCLIB lyrics.\n");
    println!("\x1b[1mUSAGE:\x1b[0m");
    println!("  mediafetch [PRESET] [URL]");
    println!("  mediafetch [URL]\n");
    println!("\x1b[1mEXAMPLES:\x1b[0m");
    println!("  mediafetch                                # Auto-detects URL from clipboard or opens prompt");
    println!("  mediafetch https://youtu.be/...           # Inspects URL and opens TUI with default 'video' preset");
    println!("  mediafetch music https://youtu.be/...     # Pre-selects 'music' preset (320k MP3 + LRCLIB lyrics)");
    println!("  mediafetch flac                           # Pre-selects FLAC and grabs URL from clipboard\n");
    println!("\x1b[1mSMART PRESETS:\x1b[0m");
    for (i, p) in PresetType::ALL.iter().enumerate() {
        println!("  \x1b[1;33m[{}]\x1b[0m \x1b[1;37m{:<12}\x1b[0m {:<22} \x1b[90m{}\x1b[0m", i + 1, p.title(), p.badge(), p.description());
    }
    println!("\n\x1b[1mDESTINATIONS:\x1b[0m");
    println!("  Videos / Shorts / Archive : ~/Videos/Downloads");
    println!("  Music / FLAC / Podcast   : ~/Music/Downloads\n");
}

#[tokio::main]
async fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();

    let mut initial_url = String::new();
    let mut initial_preset = None;

    for arg in &args {
        if arg == "--help" || arg == "-h" {
            print_help();
            return Ok(());
        } else if let Some(p) = PresetType::from_str_loose(arg) {
            initial_preset = Some(p);
        } else if arg.starts_with("http://") || arg.starts_with("https://") {
            initial_url = arg.clone();
        }
    }

    // Auto-detect from clipboard if no URL provided as argument
    if initial_url.is_empty() {
        if let Some(clip_url) = get_clipboard_url() {
            initial_url = clip_url;
        }
    }

    // Terminal Initialization
    enable_raw_mode()?;
    let mut stdout_handle = stdout();
    execute!(stdout_handle, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout_handle);
    let mut terminal = Terminal::new(backend)?;

    let mut app = AppState::new(initial_url.clone(), initial_preset);

    let (tx, mut rx) = mpsc::unbounded_channel::<DownloadProgress>();

    // If we have an initial URL, kick off metadata inspection in background
    if !app.url.is_empty() {
        app.resolving = true;
        let url_clone = app.url.clone();
        let tx_meta = tx.clone();
        tokio::spawn(async move {
            if let Ok(meta) = MediaMetadata::fetch(&url_clone).await {
                let _ = tx_meta.send(DownloadProgress::MetadataLoaded(meta));
            }
        });
    }

    let mut completed_summary: Option<DownloadSummary> = None;

    // Main event loop
    loop {
        terminal.draw(|f| ui::render(f, &app))?;

        // Handle async download updates
        while let Ok(progress) = rx.try_recv() {
            match progress {
                DownloadProgress::ResolvingMetadata => {
                    app.resolving = true;
                    app.current_step = "Resolving stream info...".to_string();
                }
                DownloadProgress::MetadataLoaded(meta) => {
                    app.resolving = false;
                    app.current_step = format!("Ready: {}", meta.display_title());
                    app.metadata = Some(meta);
                }
                DownloadProgress::Downloading { percent, speed, eta, size } => {
                    app.downloading = true;
                    app.download_percent = percent;
                    app.download_speed = speed;
                    app.download_eta = eta;
                    app.download_size = size;
                    app.current_step = format!("Downloading stream ({:.1}%)", percent);
                }
                DownloadProgress::ProcessingStep(step) => {
                    app.current_step = step;
                }
                DownloadProgress::Complete(summary) => {
                    completed_summary = Some(summary);
                    break;
                }
                DownloadProgress::Failed(err) => {
                    app.downloading = false;
                    app.error_message = Some(err);
                }
            }
        }

        if completed_summary.is_some() {
            break;
        }

        // Handle keyboard input (non-blocking with 30ms poll for high responsiveness)
        if crossterm::event::poll(Duration::from_millis(30))? {
            if let Event::Key(key) = crossterm::event::read()? {
                if app.input_mode {
                    match key.code {
                        KeyCode::Enter => {
                            if !app.input_buffer.trim().is_empty() {
                                app.url = app.input_buffer.trim().to_string();
                                app.input_mode = false;
                                app.resolving = true;
                                let url = app.url.clone();
                                let tx_meta = tx.clone();
                                tokio::spawn(async move {
                                    if let Ok(meta) = MediaMetadata::fetch(&url).await {
                                        let _ = tx_meta.send(DownloadProgress::MetadataLoaded(meta));
                                    }
                                });
                            }
                        }
                        KeyCode::Esc => {
                            if app.url.is_empty() {
                                break;
                            }
                            app.input_mode = false;
                        }
                        KeyCode::Backspace => {
                            app.input_buffer.pop();
                        }
                        KeyCode::Char(c) => {
                            app.input_buffer.push(c);
                        }
                        _ => {}
                    }
                } else {
                    match key.code {
                        KeyCode::Char('q') | KeyCode::Esc => {
                            break;
                        }
                        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                            break;
                        }
                        KeyCode::Char('j') | KeyCode::Down => {
                            if !app.downloading {
                                app.next_preset();
                            }
                        }
                        KeyCode::Char('k') | KeyCode::Up => {
                            if !app.downloading {
                                app.prev_preset();
                            }
                        }
                        KeyCode::Char('1') => app.set_preset_by_idx(0),
                        KeyCode::Char('2') => app.set_preset_by_idx(1),
                        KeyCode::Char('3') => app.set_preset_by_idx(2),
                        KeyCode::Char('4') => app.set_preset_by_idx(3),
                        KeyCode::Char('5') => app.set_preset_by_idx(4),
                        KeyCode::Char('6') => app.set_preset_by_idx(5),
                        KeyCode::Char('u') => {
                            if !app.downloading {
                                app.input_buffer = app.url.clone();
                                app.input_mode = true;
                            }
                        }
                        KeyCode::Enter => {
                            if !app.downloading && !app.url.trim().is_empty() {
                                app.downloading = true;
                                app.error_message = None;
                                let url = app.url.clone();
                                let preset = app.selected_preset();
                                let meta = app.metadata.clone().unwrap_or_default();
                                let tx_dl = tx.clone();

                                tokio::spawn(async move {
                                    let _ = Downloader::run(url, preset, meta, tx_dl).await;
                                });
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
    }

    // Clean terminal restoration
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, Show)?;
    terminal.show_cursor()?;

    // Post-exit ending / summary screen
    if let Some(ref summary) = completed_summary {
        print_nerdy_summary(summary);
        send_desktop_notification(summary);
    }

    Ok(())
}
