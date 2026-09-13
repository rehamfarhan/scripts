use ratatui::layout::Rect;
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Frame;
use std::fs;

use crate::model::{format_playtime, format_relative_time, format_star_rating};
use crate::scanner::format_file_size;
use crate::ui::app::App;
use crate::ui::theme::{
    style_border, style_meta_label, style_meta_val, BORDER_TYPE, COLOR_CYAN, COLOR_DARK_GREY,
    COLOR_GREEN, COLOR_GREY, COLOR_PURPLE, COLOR_YELLOW,
};

pub fn render_inspector(f: &mut Frame, app: &App, area: Rect) {
    let Some(game) = app.selected_game() else {
        let empty_block = Block::default()
            .borders(Borders::ALL)
            .border_type(BORDER_TYPE)
            .border_style(style_border())
            .title(" Game Telemetry & Specs ");

        let empty_text = Paragraph::new("\n  No game selected or library is empty.")
            .style(Style::default().fg(COLOR_GREY))
            .block(empty_block);
        f.render_widget(empty_text, area);
        return;
    };

    let game_stats = app.stats.get_stat(&game.dir);
    let rating = game_stats.map(|s| s.rating).unwrap_or(0);
    let playtime = game_stats.map(|s| s.playtime_seconds).unwrap_or(0);
    let play_count = game_stats.map(|s| s.play_count).unwrap_or(0);
    let last_played_iso = game_stats.and_then(|s| s.last_played.as_deref());

    let folder_path = app.games_root.join(&game.dir);
    let bin_path = folder_path.join(&game.binary);
    let bin_size_str = bin_path
        .metadata()
        .map(|m| format_file_size(m.len()))
        .unwrap_or_else(|_| "Unknown".to_string());

    let is_custom = game.custom_wrapper.unwrap_or(false) || {
        let script_file = folder_path.join("start_game.sh");
        if script_file.is_file() {
            fs::read_to_string(&script_file)
                .map(|c| c.contains("# CUSTOM_WRAPPER"))
                .unwrap_or(false)
        } else {
            false
        }
    };

    let platform_label = if game.is_windows {
        "Windows (Wine / Proton)"
    } else {
        "Linux Native"
    };

    let opts = game.wine_opts.as_ref();
    let sdl_driver = opts
        .and_then(|o| o.sdl_driver.as_deref())
        .unwrap_or("System Default (Auto)");

    let keyd_patch = opts
        .and_then(|o| o.keyd_remap.as_deref())
        .unwrap_or("Disabled");

    let resolution = opts
        .and_then(|o| o.resolution.as_deref())
        .unwrap_or("Native Fullscreen");

    let dxvk_hud = opts
        .and_then(|o| o.dxvk_hud.as_deref())
        .unwrap_or("Off");

    let wine_prefix_str = if game.is_windows {
        if let Some(ref p) = game.wine_prefix {
            if p.contains(&game.dir) {
                "Isolated Per-Game Prefix (~/.wine)"
            } else {
                "Shared Wine Prefix (~/.wine)"
            }
        } else {
            "Shared Wine Prefix (~/.wine)"
        }
    } else {
        "N/A (Native Linux)"
    };

    let lines = vec![
        // 1. Header Banner
        Line::from(vec![
            Span::styled(
                format!(" 🎮 {} ", game.display_name),
                Style::default()
                    .fg(COLOR_CYAN)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                format!("[ {} ] ", platform_label),
                Style::default()
                    .fg(if game.is_windows { COLOR_CYAN } else { COLOR_GREEN })
                    .add_modifier(Modifier::BOLD),
            ),
            if is_custom {
                Span::styled(
                    "◆ CUSTOM WRAPPER ",
                    Style::default()
                        .fg(COLOR_YELLOW)
                        .add_modifier(Modifier::BOLD),
                )
            } else {
                Span::styled("● READY ", Style::default().fg(COLOR_GREEN))
            },
        ]),
        Line::from(""),

        // 2. Section: Telemetry & Activity Showcase
        Line::from(vec![
            Span::styled("─── 📊 Session & Rating Showcase ──────────────────────────────────", Style::default().fg(COLOR_DARK_GREY)),
        ]),
        Line::from(vec![
            Span::styled("  ⭐ Star Rating:      ", style_meta_label()),
            Span::styled(
                format_star_rating(rating),
                if rating > 0 {
                    Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(COLOR_GREY)
                },
            ),
        ]),
        Line::from(vec![
            Span::styled("  ⌛ Total Playtime:   ", style_meta_label()),
            Span::styled(
                format_playtime(playtime),
                Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD),
            ),
            Span::styled(format!("  (Total Sessions: {})", play_count), Style::default().fg(COLOR_GREY)),
        ]),
        Line::from(vec![
            Span::styled("  🕒 Last Played:      ", style_meta_label()),
            Span::styled(
                format_relative_time(last_played_iso),
                Style::default().fg(Color::White),
            ),
            if let Some(iso) = last_played_iso {
                Span::styled(format!("  [{}]", iso), Style::default().fg(COLOR_GREY))
            } else {
                Span::raw("")
            },
        ]),
        Line::from(""),

        // 3. Section: Technical Specifications & Execution
        Line::from(vec![
            Span::styled("─── ⚙️ Technical & Execution Specs ─────────────────────────────────", Style::default().fg(COLOR_DARK_GREY)),
        ]),
        Line::from(vec![
            Span::styled("  📁 Game Folder:      ", style_meta_label()),
            Span::styled(format!("~/Games/{}", game.dir), style_meta_val()),
        ]),
        Line::from(vec![
            Span::styled("  📄 Executable:       ", style_meta_label()),
            Span::styled(&game.binary, style_meta_val()),
            Span::styled(format!("  (Size: {})", bin_size_str), Style::default().fg(COLOR_GREY)),
        ]),
        Line::from(vec![
            Span::styled("  🐧 SDL Video Driver: ", style_meta_label()),
            Span::styled(sdl_driver, style_meta_val()),
        ]),
        if game.is_windows {
            Line::from(vec![
                Span::styled("  🍷 Wine Prefix:      ", style_meta_label()),
                Span::styled(wine_prefix_str, style_meta_val()),
            ])
        } else {
            Line::raw("")
        },
        if game.is_windows {
            Line::from(vec![
                Span::styled("  🖥️ Virtual Desktop:  ", style_meta_label()),
                Span::styled(resolution, style_meta_val()),
                Span::styled("  | DXVK HUD: ", style_meta_label()),
                Span::styled(dxvk_hud, style_meta_val()),
            ])
        } else {
            Line::raw("")
        },
        Line::from(vec![
            Span::styled("  ⌨️ Keyboard Patch:   ", style_meta_label()),
            Span::styled(
                keyd_patch,
                if keyd_patch != "Disabled" {
                    Style::default().fg(COLOR_PURPLE).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(COLOR_GREY)
                },
            ),
            if keyd_patch != "Disabled" {
                Span::styled(" (Auto keyd bind on start, reset on exit)", Style::default().fg(COLOR_GREY))
            } else {
                Span::raw("")
            },
        ]),
    ];

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border())
        .title(" Game Telemetry & Specs ");

    let widget = Paragraph::new(lines).block(block);
    f.render_widget(widget, area);
}
