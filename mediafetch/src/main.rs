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

fn pad_cell(s: &str, target_width: usize) -> String {
    use unicode_width::{UnicodeWidthChar, UnicodeWidthStr};
    let w = UnicodeWidthStr::width(s);
    if w >= target_width {
        let mut truncated = String::new();
        let mut cur_w = 0;
        let max_w = target_width.saturating_sub(1);
        for c in s.chars() {
            let cw = UnicodeWidthChar::width(c).unwrap_or(0);
            if cur_w + cw > max_w {
                truncated.push('…');
                cur_w += 1;
                break;
            }
            truncated.push(c);
            cur_w += cw;
        }
        while cur_w < target_width {
            truncated.push(' ');
            cur_w += 1;
        }
        truncated
    } else {
        let mut res = s.to_string();
        for _ in 0..(target_width - w) {
            res.push(' ');
        }
        res
    }
}

fn print_nerdy_summary(summary: &DownloadSummary) {
    use unicode_width::UnicodeWidthStr;

    const BORDER: &str = "\x1b[38;5;37m";     // Clean teal/cyan frame
    const BORDER_DIM: &str = "\x1b[38;5;239m"; // Subtle inner divider
    const RESET: &str = "\x1b[0m";
    const BOX_WIDTH: usize = 98;
    const INNER_WIDTH: usize = BOX_WIDTH - 2;

    let is_audio = summary.preset.should_fetch_lyrics() || summary.preset == PresetType::Podcast;
    let media_type_label = if is_audio { "1 Audio" } else { "1 Video" };
    let col2_header = if is_audio { "Track Title" } else { "Video Title" };

    // Format fields
    let format_str = match summary.preset {
        PresetType::Video => "1080p H.265",
        PresetType::Music => "320k MP3",
        PresetType::Flac => "FLAC",
        PresetType::Shorts => "1080p MP4",
        PresetType::Podcast => "Opus",
        PresetType::Archive => "Best Quality",
    };

    let status_str = if summary.lrc_path.is_some() {
        "✓ Saved"
    } else {
        "✓ Saved"
    };

    let speed_str = if !summary.speed.is_empty() && summary.speed != "0.0 MB/s" && summary.speed != "-- KiB/s" {
        summary.speed.clone()
    } else {
        let elapsed = summary.duration.as_secs_f64();
        if elapsed > 0.05 && summary.file_size_bytes > 0 {
            let mb_per_sec = (summary.file_size_bytes as f64 / 1_000_000.0) / elapsed;
            format!("{:.1} MB/s", mb_per_sec)
        } else {
            "0.3 MB/s".to_string()
        }
    };

    let total_secs = summary.duration.as_secs();
    let dur_str = format!("{:02}:{:02}", total_secs / 60, total_secs % 60);

    let home = dirs::home_dir().unwrap_or_default();
    let target_dir = summary.file_path.parent().unwrap_or(&summary.file_path);
    let dir_str = if let Ok(rel) = target_dir.strip_prefix(&home) {
        format!("~/{}", rel.to_string_lossy())
    } else {
        target_dir.to_string_lossy().to_string()
    };

    // 1. Top border with title
    let title_prefix = format!("╭── 📥 Download Complete • {} ", media_type_label);
    let title_prefix_width = UnicodeWidthStr::width(title_prefix.as_str());
    let top_dashes = BOX_WIDTH.saturating_sub(title_prefix_width + 1);
    println!();
    println!(
        "{}{}{}{}{}{}",
        BORDER,
        title_prefix,
        BORDER,
        "─".repeat(top_dashes),
        BORDER,
        "╮\x1b[0m"
    );

    // 2. Padding line
    println!("{}│{}│{}", BORDER, " ".repeat(INNER_WIDTH), RESET);

    // 3. Table Column Headers: # (6), Title (46), Format (16), Size (14), Status (14) = 96
    let h_num = pad_cell("  #", 6);
    let h_title = pad_cell(col2_header, 46);
    let h_format = pad_cell("Format", 16);
    let h_size = pad_cell("Size", 14);
    let h_status = pad_cell("Status", 14);

    println!(
        "{}│\x1b[90m{}\x1b[1;37m{}\x1b[1;37m{}\x1b[1;37m{}\x1b[1;37m{}{}\x1b[0m",
        BORDER, h_num, h_title, h_format, h_size, h_status, format!("{}│", BORDER)
    );

    // 4. Horizontal table divider
    println!(
        "{}│  {}{}{}  {}│\x1b[0m",
        BORDER,
        BORDER_DIM,
        "─".repeat(INNER_WIDTH - 4),
        BORDER,
        BORDER
    );

    // 5. Data row
    let cell_num = pad_cell("  01", 6);
    let cell_title = pad_cell(&summary.title, 46);
    let cell_format = pad_cell(format_str, 16);
    let cell_size = pad_cell(&summary.formatted_size, 14);
    let cell_status = pad_cell(status_str, 14);

    println!(
        "{}│\x1b[90m{}\x1b[1;37m{}\x1b[36m{}\x1b[37m{}\x1b[1;32m{}{}\x1b[0m",
        BORDER, cell_num, cell_title, cell_format, cell_size, cell_status, format!("{}│", BORDER)
    );

    // 6. Padding line
    println!("{}│{}│{}", BORDER, " ".repeat(INNER_WIDTH), RESET);

    // 7. Bottom border with stats pills
    // Plain string for measurement
    let plain_pills = format!(
        " ⏱ {} │ 📦 {} │ 🚀 {} │ ✅ 1/1 Saved │ 📁 {} ",
        dur_str, summary.formatted_size, speed_str, dir_str
    );
    let pills_width = UnicodeWidthStr::width(plain_pills.as_str());

    let remaining_border = BOX_WIDTH.saturating_sub(pills_width + 2);
    let left_dashes = remaining_border / 2;
    let right_dashes = remaining_border.saturating_sub(left_dashes);

    // Colored pills
    let colored_pills = format!(
        " \x1b[37m⏱ {}\x1b[0m {}│\x1b[0m \x1b[33m📦 {}\x1b[0m {}│\x1b[0m \x1b[36m🚀 {}\x1b[0m {}│\x1b[0m \x1b[1;32m✅ 1/1 Saved\x1b[0m {}│\x1b[0m \x1b[34m📁 {}\x1b[0m ",
        dur_str, BORDER_DIM, summary.formatted_size, BORDER_DIM, speed_str, BORDER_DIM, BORDER_DIM, dir_str
    );

    println!(
        "{}{}{}{}{}{}{}\x1b[0m",
        BORDER,
        "╰",
        "─".repeat(left_dashes),
        colored_pills,
        BORDER,
        "─".repeat(right_dashes),
        "╯"
    );
    println!();
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
