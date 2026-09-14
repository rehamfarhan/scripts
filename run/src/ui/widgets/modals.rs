use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, List, ListItem, Paragraph};
use ratatui::Frame;

use crate::scanner::{evaluate_binary_score, format_file_size};
use crate::ui::app::{ActiveModal, App};
use crate::ui::theme::{
    style_border_active, BORDER_TYPE, COLOR_BG_POPUP, COLOR_CYAN, COLOR_DARK_GREY, COLOR_GREEN,
    COLOR_GREY, COLOR_YELLOW,
};

fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}

pub fn render_modals(f: &mut Frame, app: &App, area: Rect) {
    match &app.active_modal {
        ActiveModal::None => {}
        ActiveModal::RateGame { selected_opt } => {
            render_rate_modal(f, *selected_opt, area);
        }
        ActiveModal::KeyboardPatch {
            selected_opt,
            custom_input,
            is_custom_mode,
        } => {
            render_keyd_modal(f, *selected_opt, custom_input, *is_custom_mode, area);
        }
        ActiveModal::ExecutionSettings {
            selected_opt,
            is_windows,
            opts,
        } => {
            render_exec_modal(f, *selected_opt, *is_windows, opts, area);
        }
        ActiveModal::ChangeBinary {
            binaries,
            filtered_indices,
            selected_bin,
            search_query,
        } => {
            render_change_binary_modal(
                f,
                app,
                binaries,
                filtered_indices,
                *selected_bin,
                search_query,
                area,
            );
        }
        ActiveModal::RenameGame { input } => {
            render_rename_modal(f, input, area);
        }
        ActiveModal::NewGameWizard {
            folders,
            current_idx,
            binaries,
            filtered_indices,
            selected_bin,
            search_query,
            is_searching,
        } => {
            render_wizard_modal(
                f,
                folders,
                *current_idx,
                binaries,
                filtered_indices,
                *selected_bin,
                search_query,
                *is_searching,
                area,
            );
        }
    }
}

fn render_rate_modal(f: &mut Frame, selected: usize, area: Rect) {
    let popup_area = centered_rect(56, 52, area);
    f.render_widget(Clear, popup_area);

    let options = [
        "🌟🌟🌟🌟🌟  10/10  (Masterpiece)",
        "🌟🌟🌟🌟⭐️  9/10   (Exceptional)",
        "🌟🌟🌟🌟⬛  8/10   (Great)",
        "🌟🌟🌟⭐️⬛  7/10   (Very Good)",
        "🌟🌟🌟⬛⬛  6/10   (Good)",
        "🌟🌟⭐️⬛⬛  5/10   (Decent)",
        "🌟🌟⬛⬛⬛  4/10   (Mediocre)",
        "🌟⭐️⬛⬛⬛  3/10   (Poor)",
        "🌟⬛⬛⬛⬛  2/10   (Bad)",
        "⭐️⬛⬛⬛⬛  1/10   (Terrible)",
        "⬛⬛⬛⬛⬛  0/10   (Unrated)",
    ];

    let items: Vec<ListItem> = options
        .iter()
        .enumerate()
        .map(|(idx, opt)| {
            let is_sel = idx == selected;
            let line = Line::from(vec![
                Span::styled(if is_sel { "▶ " } else { "  " }, Style::default().fg(COLOR_CYAN)),
                Span::styled(
                    *opt,
                    if is_sel {
                        Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(Color::White)
                    },
                ),
            ]);
            ListItem::new(line)
        })
        .collect();

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border_active())
        .title(" ⭐ Rate Game [Use ↑/↓, Enter: Save, Esc: Cancel] ")
        .style(Style::default().bg(COLOR_BG_POPUP));

    let list = List::new(items).block(block);
    f.render_widget(list, popup_area);
}

fn render_keyd_modal(
    f: &mut Frame,
    selected: usize,
    custom_input: &str,
    is_custom_mode: bool,
    area: Rect,
) {
    let popup_area = centered_rect(60, 42, area);
    f.render_widget(Clear, popup_area);

    let options = [
        "1) Disabled / None [Default]",
        "2) Map Left Shift -> Left Ctrl (leftshift=leftcontrol)",
        "3) Custom keyd binding...",
    ];

    let mut lines = Vec::new();
    lines.push(Line::from(vec![
        Span::styled(
            "Temporarily remaps broken keys in-game and restores defaults on exit.",
            Style::default().fg(COLOR_GREY),
        ),
    ]));
    lines.push(Line::from(""));

    for (idx, opt) in options.iter().enumerate() {
        let is_sel = idx == selected;
        lines.push(Line::from(vec![
            Span::styled(if is_sel { " ▶ " } else { "   " }, Style::default().fg(COLOR_CYAN)),
            Span::styled(
                *opt,
                if is_sel {
                    Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(Color::White)
                },
            ),
        ]));
    }

    if is_custom_mode {
        lines.push(Line::from(""));
        lines.push(Line::from(vec![
            Span::styled("  Custom Binding: ", Style::default().fg(COLOR_YELLOW)),
            Span::styled(custom_input, Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            Span::styled("█", Style::default().fg(COLOR_CYAN)),
        ]));
    }

    lines.push(Line::from(""));
    lines.push(Line::from(vec![
        Span::styled(" [Enter] Save   [Esc] Cancel", Style::default().fg(COLOR_DARK_GREY)),
    ]));

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border_active())
        .title(" ⌨️ Keyboard Patches (keyd) ")
        .style(Style::default().bg(COLOR_BG_POPUP));

    let paragraph = Paragraph::new(lines).block(block);
    f.render_widget(paragraph, popup_area);
}

fn render_exec_modal(
    f: &mut Frame,
    selected: usize,
    is_windows: bool,
    opts: &crate::model::WineOpts,
    area: Rect,
) {
    let popup_area = centered_rect(65, 55, area);
    f.render_widget(Clear, popup_area);

    let mut lines = Vec::new();
    lines.push(Line::from(vec![
        Span::styled("Configure video drivers and compatibility settings for this game:", Style::default().fg(COLOR_GREY)),
    ]));
    lines.push(Line::from(""));

    if !is_windows {
        let options = [
            ("SDL Video Driver: Auto / System Default", opts.sdl_driver.is_none()),
            ("SDL Video Driver: Force X11 (Xwayland compatibility)", opts.sdl_driver.as_deref() == Some("x11")),
            ("SDL Video Driver: Force Wayland", opts.sdl_driver.as_deref() == Some("wayland")),
        ];

        for (idx, (label, is_current)) in options.iter().enumerate() {
            let is_sel = idx == selected;
            lines.push(Line::from(vec![
                Span::styled(if is_sel { " ▶ " } else { "   " }, Style::default().fg(COLOR_CYAN)),
                Span::styled(
                    *label,
                    if is_sel {
                        Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(Color::White)
                    },
                ),
                if *is_current {
                    Span::styled("  [Active]", Style::default().fg(COLOR_GREEN))
                } else {
                    Span::raw("")
                },
            ]));
        }
    } else {
        let current_res = opts.resolution.as_deref().unwrap_or("Native Fullscreen");
        let current_hud = opts.dxvk_hud.as_deref().unwrap_or("Off");
        let current_sdl = opts.sdl_driver.as_deref().unwrap_or("Auto");

        let items = [
            format!("Virtual Desktop Resolution: {}", current_res),
            format!("DXVK Performance HUD: {}", current_hud),
            format!("Wine SDL Video Driver: {}", current_sdl),
        ];

        for (idx, label) in items.iter().enumerate() {
            let is_sel = idx == selected;
            lines.push(Line::from(vec![
                Span::styled(if is_sel { " ▶ " } else { "   " }, Style::default().fg(COLOR_CYAN)),
                Span::styled(
                    label.clone(),
                    if is_sel {
                        Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(Color::White)
                    },
                ),
            ]));
        }
        lines.push(Line::from(""));
        lines.push(Line::from(vec![
            Span::styled("  Press [Space] to cycle selected option value.", Style::default().fg(COLOR_YELLOW)),
        ]));
    }

    lines.push(Line::from(""));
    lines.push(Line::from(vec![
        Span::styled(" [Enter] Save Settings   [Esc] Cancel", Style::default().fg(COLOR_DARK_GREY)),
    ]));

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border_active())
        .title(" ⚙️ Execution & Video Driver Settings ")
        .style(Style::default().bg(COLOR_BG_POPUP));

    let paragraph = Paragraph::new(lines).block(block);
    f.render_widget(paragraph, popup_area);
}

fn render_change_binary_modal(
    f: &mut Frame,
    app: &App,
    binaries: &[std::path::PathBuf],
    filtered_indices: &[usize],
    selected: usize,
    search_query: &str,
    area: Rect,
) {
    let popup_area = centered_rect(80, 70, area);
    f.render_widget(Clear, popup_area);

    let popup_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(5)])
        .split(popup_area);

    // Search bar
    let search_content = Line::from(vec![
        Span::styled("🔍 ", Style::default().fg(COLOR_YELLOW)),
        if search_query.is_empty() {
            Span::styled("Type to filter executables (e.g. x86_64, exe, start)...", Style::default().fg(COLOR_DARK_GREY))
        } else {
            Span::styled(search_query, Style::default().fg(Color::White).add_modifier(Modifier::BOLD))
        },
        Span::styled("█", Style::default().fg(COLOR_CYAN)),
    ]);

    let search_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border_active())
        .title(" Filter Executables ")
        .style(Style::default().bg(COLOR_BG_POPUP));

    let search_widget = Paragraph::new(search_content).block(search_block);
    f.render_widget(search_widget, popup_chunks[0]);

    // Binary list with viewport windowing
    let game_dir = app
        .selected_game()
        .map(|g| app.games_root.join(&g.dir))
        .unwrap_or_else(|| app.games_root.clone());

    let list_height = popup_chunks[1].height.saturating_sub(2) as usize;
    let visible_count = list_height.max(1);
    let total_items = filtered_indices.len();

    let offset = if selected < visible_count {
        0
    } else {
        selected + 1 - visible_count
    };
    let end = (offset + visible_count).min(total_items);
    let visible_slice = if total_items > 0 && offset < total_items {
        &filtered_indices[offset..end]
    } else {
        &[]
    };

    let items: Vec<ListItem> = visible_slice
        .iter()
        .enumerate()
        .map(|(rel_idx, &bin_idx)| {
            let actual_idx = offset + rel_idx;
            let bin = &binaries[bin_idx];
            let is_sel = actual_idx == selected;
            let rel = bin.strip_prefix(&game_dir).unwrap_or(bin);
            let size = bin.metadata().map(|m| format_file_size(m.len())).unwrap_or_else(|_| "Unknown".to_string());
            let (_, tag) = evaluate_binary_score(&game_dir, bin);

            let line = Line::from(vec![
                Span::styled(if is_sel { "▶ " } else { "  " }, Style::default().fg(COLOR_CYAN)),
                Span::styled(format!("{:<30} ", rel.display()), if is_sel { Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD) } else { Style::default().fg(Color::White) }),
                Span::styled(format!("{:>10} ", size), Style::default().fg(COLOR_GREY)),
                Span::styled(tag, if tag.starts_with('⭐') { Style::default().fg(COLOR_YELLOW) } else { Style::default().fg(COLOR_DARK_GREY) }),
            ]);
            ListItem::new(line)
        })
        .collect();

    let pos_text = if total_items > 0 {
        format!("{}/{}", selected + 1, total_items)
    } else {
        "0/0".to_string()
    };
    let scroll_hint = if total_items > visible_count {
        let up = if offset > 0 { "▲" } else { " " };
        let down = if end < total_items { "▼" } else { " " };
        format!(" {} {} ", up, down)
    } else {
        String::new()
    };

    let title = format!(" 🛠️ Select Executable ({}){} [Enter: Choose | Esc: Cancel] ", pos_text, scroll_hint);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border_active())
        .title(title)
        .style(Style::default().bg(COLOR_BG_POPUP));

    let list = List::new(items).block(block);
    f.render_widget(list, popup_chunks[1]);
}

fn render_rename_modal(f: &mut Frame, input: &str, area: Rect) {
    let popup_area = centered_rect(55, 25, area);
    f.render_widget(Clear, popup_area);

    let lines = vec![
        Line::from(""),
        Line::from(vec![
            Span::styled("  New Display Name: ", Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
            Span::styled(input, Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            Span::styled("█", Style::default().fg(COLOR_CYAN)),
        ]),
        Line::from(""),
        Line::from(vec![
            Span::styled("  [Enter] Confirm Rename   [Esc] Cancel", Style::default().fg(COLOR_DARK_GREY)),
        ]),
    ];

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border_active())
        .title(" ✏️ Rename Game Entry ")
        .style(Style::default().bg(COLOR_BG_POPUP));

    let widget = Paragraph::new(lines).block(block);
    f.render_widget(widget, popup_area);
}

fn render_wizard_modal(
    f: &mut Frame,
    folders: &[std::path::PathBuf],
    current_idx: usize,
    binaries: &[std::path::PathBuf],
    filtered_indices: &[usize],
    selected_bin: usize,
    search_query: &str,
    is_searching: bool,
    area: Rect,
) {
    let popup_area = centered_rect(80, 70, area);
    f.render_widget(Clear, popup_area);

    let total_folders = folders.len();
    let current_folder = &folders[current_idx];
    let folder_name = current_folder.file_name().unwrap_or_default().to_string_lossy();

    let popup_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(5)])
        .split(popup_area);

    // Search bar
    let search_content = Line::from(vec![
        Span::styled("🔍 ", Style::default().fg(COLOR_YELLOW)),
        if search_query.is_empty() && !is_searching {
            Span::styled("Press / to filter binaries...", Style::default().fg(COLOR_DARK_GREY))
        } else if search_query.is_empty() {
            Span::styled("Type to filter binaries (e.g. x86_64, exe, start)...", Style::default().fg(COLOR_DARK_GREY))
        } else {
            Span::styled(search_query, Style::default().fg(Color::White).add_modifier(Modifier::BOLD))
        },
        if is_searching {
            Span::styled("█", Style::default().fg(COLOR_CYAN))
        } else {
            Span::raw("")
        },
    ]);

    let search_title = format!(" 📁 New Folder ({}/{}): {} ", current_idx + 1, total_folders, folder_name);
    let search_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(if is_searching { style_border_active() } else { Style::default().fg(COLOR_DARK_GREY) })
        .title(search_title)
        .style(Style::default().bg(COLOR_BG_POPUP));

    let search_widget = Paragraph::new(search_content).block(search_block);
    f.render_widget(search_widget, popup_chunks[0]);

    // Binary list with viewport windowing
    let list_height = popup_chunks[1].height.saturating_sub(2) as usize;
    let visible_count = list_height.max(1);
    let total_items = filtered_indices.len();

    let offset = if selected_bin < visible_count {
        0
    } else {
        selected_bin + 1 - visible_count
    };
    let end = (offset + visible_count).min(total_items);
    let visible_slice = if total_items > 0 && offset < total_items {
        &filtered_indices[offset..end]
    } else {
        &[]
    };

    let items: Vec<ListItem> = visible_slice
        .iter()
        .enumerate()
        .map(|(rel_idx, &bin_idx)| {
            let actual_idx = offset + rel_idx;
            let bin = &binaries[bin_idx];
            let is_sel = actual_idx == selected_bin;
            let rel = bin.strip_prefix(current_folder).unwrap_or(bin);
            let size = bin.metadata().map(|m| format_file_size(m.len())).unwrap_or_else(|_| "Unknown".to_string());
            let (_, tag) = evaluate_binary_score(current_folder, bin);

            let line = Line::from(vec![
                Span::styled(if is_sel { "▶ " } else { "  " }, Style::default().fg(COLOR_CYAN)),
                Span::styled(format!("{:<30} ", rel.display()), if is_sel { Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD) } else { Style::default().fg(Color::White) }),
                Span::styled(format!("{:>10} ", size), Style::default().fg(COLOR_GREY)),
                Span::styled(tag, if tag.starts_with('⭐') { Style::default().fg(COLOR_YELLOW) } else { Style::default().fg(COLOR_DARK_GREY) }),
            ]);
            ListItem::new(line)
        })
        .collect();

    let pos_text = if total_items > 0 {
        format!("{}/{}", selected_bin + 1, total_items)
    } else {
        "0/0".to_string()
    };
    let scroll_hint = if total_items > visible_count {
        let up = if offset > 0 { "▲" } else { " " };
        let down = if end < total_items { "▼" } else { " " };
        format!(" {} {} ", up, down)
    } else {
        String::new()
    };

    let footer_hints = if is_searching {
        "[Enter: Choose | Esc: Selection Mode]"
    } else {
        "[Enter: Add Game | s: Skip | i: Ignore | /: Search]"
    };

    let title = format!(" 🧙 Select Main Binary ({}){} {} ", pos_text, scroll_hint, footer_hints);
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(if !is_searching { style_border_active() } else { Style::default().fg(COLOR_DARK_GREY) })
        .title(title)
        .style(Style::default().bg(COLOR_BG_POPUP));

    let list = List::new(items).block(block);
    f.render_widget(list, popup_chunks[1]);
}
