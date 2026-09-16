use ratatui::layout::Rect;
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Frame;

use crate::ui::app::App;
use crate::ui::theme::{
    style_border, style_keybind, BORDER_TYPE, COLOR_CYAN, COLOR_GREEN, COLOR_GREY, COLOR_PURPLE,
};

pub fn render_hotkeys(f: &mut Frame, app: &App, area: Rect) {
    let toast_opt = app.toast_text();

    let lines = vec![
        Line::from(vec![
            Span::styled(" [j/k] ", style_keybind()),
            Span::styled("Move   ", Style::default().fg(Color::White)),
            Span::styled("[g/G] ", style_keybind()),
            Span::styled("Top/End ", Style::default().fg(Color::White)),
            Span::styled("[Enter] ", style_keybind()),
            Span::styled("Launch   ", Style::default().fg(Color::White)),
            Span::styled("[s] ", style_keybind()),
            Span::styled("Field  ", Style::default().fg(Color::White)),
            Span::styled("[S] ", style_keybind()),
            Span::styled("▲▼  ", Style::default().fg(Color::White)),
            Span::styled("[f] ", style_keybind()),
            Span::styled("Fav   ", Style::default().fg(Color::White)),
            Span::styled("[r] ", style_keybind()),
            Span::styled("Rate   ", Style::default().fg(Color::White)),
            Span::styled("[p] ", style_keybind()),
            Span::styled("Keyd Patch", Style::default().fg(Color::White)),
        ]),
        Line::from(vec![
            Span::styled(" [c]   ", style_keybind()),
            Span::styled("Config ", Style::default().fg(Color::White)),
            Span::styled("[e]   ", style_keybind()),
            Span::styled("Edit   ", Style::default().fg(Color::White)),
            Span::styled("[d]     ", style_keybind()),
            Span::styled("Desktop  ", Style::default().fg(Color::White)),
            Span::styled("[o]   ", style_keybind()),
            Span::styled("Open   ", Style::default().fg(Color::White)),
            Span::styled("[m] ", style_keybind()),
            Span::styled("Change Exec  ", Style::default().fg(Color::White)),
            Span::styled("[n] ", style_keybind()),
            Span::styled("Rename   ", Style::default().fg(Color::White)),
            Span::styled("[x] ", style_keybind()),
            Span::styled("Delete   ", Style::default().fg(Color::White)),
            Span::styled("[q] ", style_keybind()),
            Span::styled("Quit", Style::default().fg(Color::White)),
        ]),
        Line::from(""),
        if let Some(toast) = toast_opt {
            Line::from(vec![
                Span::styled(" 🔔 ", Style::default().fg(COLOR_CYAN)),
                Span::styled(
                    toast,
                    Style::default()
                        .fg(COLOR_GREEN)
                        .add_modifier(Modifier::BOLD),
                ),
            ])
        } else {
            Line::from(vec![
                Span::styled(" 💡 Tip: ", Style::default().fg(COLOR_PURPLE).add_modifier(Modifier::BOLD)),
                Span::styled(
                    "Press / to instantly filter games, or press Enter to launch.",
                    Style::default().fg(COLOR_GREY),
                ),
            ])
        },
    ];

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(style_border())
        .title(" Quick Actions & Keybinds ");

    let widget = Paragraph::new(lines).block(block);
    f.render_widget(widget, area);
}
