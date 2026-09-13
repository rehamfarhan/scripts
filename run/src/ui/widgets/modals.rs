use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Clear, List, ListItem, Paragraph};
use ratatui::Frame;

use crate::scanner::{evaluate_binary_score, format_file_size};
use crate::ui::app::{ActiveModal, App, WizardStep};
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
            selected_bin,
        } => {
            render_change_binary_modal(f, app, binaries, *selected_bin, area);
        }
        ActiveModal::RenameGame { input } => {
            render_rename_modal(f, input, area);
        }
        ActiveModal::NewGameWizard {
            folders,
            current_idx,
            binaries,
            selected_bin,
            display_name,
            step,
            ..
        } => {
            render_wizard_modal(
                f,
                folders,
                *current_idx,
                binaries,
                *selected_bin,
                display_name,
                step,
                area,
            );
        }
    }
}

fn render_rate_modal(f: &mut Frame, selected: usize, area: Rect) {
    let popup_area = centered_rect(50, 40, area);
    f.render_widget(Clear, popup_area);

    let options = [
        "⭐⭐⭐⭐⭐  5/5 (Masterpiece)",
        "⭐⭐⭐⭐  4/5 (Great)",
        "⭐⭐⭐  3/5 (Good)",
        "⭐⭐  2/5 (Mediocre)",
        "⭐  1/5 (Bad)",
        "Unrated (0/5)",
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
        .title(" ⭐ Rate Game [Use ↑/↓, Enter to Save, Esc to Cancel] ")
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
    selected: usize,
    area: Rect,
) {
    let popup_area = centered_rect(75, 65, area);
    f.render_widget(Clear, popup_area);

    let game_dir = app
        .selected_game()
        .map(|g| app.games_root.join(&g.dir))
        .unwrap_or_else(|| app.games_root.clone());

    let items: Vec<ListItem> = binaries
        .iter()
        .enumerate()
        .map(|(idx, bin)| {
            let is_sel = idx == selected;
            let rel = bin.strip_prefix(&game_dir).unwrap_or(bin);
            let size = bin.metadata().map(|m| format_file_size(m.len())).unwrap_or_else(|_| "Unknown".to_string());
            let (_, tag) = evaluate_binary_score(&game_dir, bin);

            let line = Line::from(vec![
                Span::styled(if is_sel { "▶ " } else { "  " }, Style::default().fg(COLOR_CYAN)),
                Span::styled(format!("{:<28} ", rel.display()), if is_sel { Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD) } else { Style::default().fg(Color::White) }),
                Span::styled(format!("{:>10} ", size), Style::default().fg(COLOR_GREY)),
                Span::styled(tag, if tag.starts_with('⭐') { Style::default().fg(COLOR_YELLOW) } else { Style::default().fg(COLOR_DARK_GREY) }),
            ]);
            ListItem::new(line)
        })
        .collect();

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border_active())
        .title(" 🛠️ Select Executable Binary [Enter: Choose | Esc: Cancel] ")
        .style(Style::default().bg(COLOR_BG_POPUP));

    let list = List::new(items).block(block);
    f.render_widget(list, popup_area);
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
    selected_bin: usize,
    display_name: &str,
    step: &WizardStep,
    area: Rect,
) {
    let popup_area = centered_rect(70, 60, area);
    f.render_widget(Clear, popup_area);

    let total = folders.len();
    let current_folder = &folders[current_idx];
    let folder_name = current_folder.file_name().unwrap_or_default().to_string_lossy();

    let mut lines = vec![
        Line::from(vec![
            Span::styled(format!("📁 New Folder Discovered ({}/{}): ", current_idx + 1, total), Style::default().fg(COLOR_YELLOW).add_modifier(Modifier::BOLD)),
            Span::styled(folder_name.to_string(), Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(""),
    ];

    match step {
        WizardStep::SelectBinary => {
            lines.push(Line::from(vec![
                Span::styled("Step 1: Select Main Executable Binary:", Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            ]));
            lines.push(Line::from(""));

            for (idx, bin) in binaries.iter().enumerate() {
                let is_sel = idx == selected_bin;
                let rel = bin.strip_prefix(current_folder).unwrap_or(bin);
                let size = bin.metadata().map(|m| format_file_size(m.len())).unwrap_or_else(|_| "".to_string());
                let (_, tag) = evaluate_binary_score(current_folder, bin);

                lines.push(Line::from(vec![
                    Span::styled(if is_sel { " ▶ " } else { "   " }, Style::default().fg(COLOR_CYAN)),
                    Span::styled(format!("{:<26} ", rel.display()), if is_sel { Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD) } else { Style::default().fg(Color::White) }),
                    Span::styled(format!("{:>8} ", size), Style::default().fg(COLOR_GREY)),
                    Span::styled(tag, if tag.starts_with('⭐') { Style::default().fg(COLOR_YELLOW) } else { Style::default().fg(COLOR_DARK_GREY) }),
                ]));
            }
            lines.push(Line::from(""));
            lines.push(Line::from(vec![
                Span::styled(" [Enter] Next Step   [s] Skip Folder   [i] Ignore Directory", Style::default().fg(COLOR_DARK_GREY)),
            ]));
        }
        WizardStep::NameGame => {
            lines.push(Line::from(vec![
                Span::styled("Step 2: Confirm Game Display Name:", Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            ]));
            lines.push(Line::from(""));
            lines.push(Line::from(vec![
                Span::styled("  Display Name: ", Style::default().fg(COLOR_YELLOW)),
                Span::styled(display_name, Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
                Span::styled("█", Style::default().fg(COLOR_CYAN)),
            ]));
            lines.push(Line::from(""));
            lines.push(Line::from(vec![
                Span::styled(" [Enter] Confirm & Next   [Backspace] Edit", Style::default().fg(COLOR_DARK_GREY)),
            ]));
        }
        WizardStep::ConfigureSettings => {
            lines.push(Line::from(vec![
                Span::styled("Step 3: Ready to Register & Generate Launcher Wrapper!", Style::default().fg(COLOR_GREEN).add_modifier(Modifier::BOLD)),
            ]));
            lines.push(Line::from(""));
            lines.push(Line::from(vec![
                Span::styled("  • Automatically generates start_game.sh wrapper with safe exit traps.", Style::default().fg(Color::White)),
            ]));
            lines.push(Line::from(vec![
                Span::styled("  • Registers game in library with zero-sudo keyd support.", Style::default().fg(Color::White)),
            ]));
            lines.push(Line::from(""));
            lines.push(Line::from(vec![
                Span::styled(" [Enter] Finish Setup & Add Game", Style::default().fg(COLOR_CYAN).add_modifier(Modifier::BOLD)),
            ]));
        }
    }

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border_active())
        .title(" 🧙 New Game Onboarding Wizard ")
        .style(Style::default().bg(COLOR_BG_POPUP));

    let widget = Paragraph::new(lines).block(block);
    f.render_widget(widget, popup_area);
}
