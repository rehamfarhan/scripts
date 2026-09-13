use ratatui::layout::{Constraint, Direction, Layout, Rect};
use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};
use ratatui::widgets::{Block, Borders, List, ListItem, Paragraph};
use ratatui::Frame;

use crate::ui::app::App;
use crate::ui::theme::{
    style_border, style_border_active, style_item_normal, style_item_selected, BORDER_TYPE,
    COLOR_CYAN, COLOR_DARK_GREY, COLOR_YELLOW,
};

pub fn render_game_list(f: &mut Frame, app: &App, area: Rect) {
    // Split into search input (3 lines) and game list (remaining)
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(5)])
        .split(area);

    // 1. Search Bar
    let search_border_style = if app.is_searching {
        style_border_active()
    } else {
        style_border()
    };

    let search_content = if app.search_query.is_empty() && !app.is_searching {
        Line::from(vec![
            Span::styled("🔍 ", Style::default().fg(COLOR_YELLOW)),
            Span::styled(
                "Search games (press / to type)...",
                Style::default().fg(COLOR_DARK_GREY),
            ),
        ])
    } else {
        Line::from(vec![
            Span::styled("🔍 ", Style::default().fg(COLOR_YELLOW)),
            Span::styled(
                &app.search_query,
                Style::default()
                    .fg(Color::White)
                    .add_modifier(Modifier::BOLD),
            ),
            if app.is_searching {
                Span::styled("█", Style::default().fg(COLOR_CYAN))
            } else {
                Span::raw("")
            },
        ])
    };

    let search_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(search_border_style)
        .title(" Library Filter ");

    let search_widget = Paragraph::new(search_content).block(search_block);
    f.render_widget(search_widget, chunks[0]);

    // 2. Game List
    let items: Vec<ListItem> = app
        .filtered_indices
        .iter()
        .enumerate()
        .map(|(display_idx, &game_idx)| {
            let game = &app.all_games[game_idx];
            let is_selected = display_idx == app.selected_index;

            let icon = game.icon.as_deref().unwrap_or(if game.is_windows {
                "💻"
            } else {
                "🐧"
            });

            let prefix = if is_selected { "▶ " } else { "  " };

            let title_span = if is_selected {
                Span::styled(
                    &game.display_name,
                    Style::default()
                        .fg(COLOR_CYAN)
                        .add_modifier(Modifier::BOLD),
                )
            } else {
                Span::styled(&game.display_name, style_item_normal())
            };

            let line = Line::from(vec![
                Span::styled(
                    prefix,
                    if is_selected {
                        Style::default().fg(COLOR_CYAN)
                    } else {
                        Style::default().fg(COLOR_DARK_GREY)
                    },
                ),
                Span::raw(format!("{} ", icon)),
                title_span,
            ]);

            ListItem::new(line).style(if is_selected {
                style_item_selected()
            } else {
                Style::default()
            })
        })
        .collect();

    let total_count = app.all_games.len();
    let filtered_count = app.filtered_indices.len();
    let title_text = if app.search_query.is_empty() {
        format!(" Games ({}) ", total_count)
    } else {
        format!(" Games ({}/{}) ", filtered_count, total_count)
    };

    let list_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BORDER_TYPE)
        .border_style(if !app.is_searching {
            style_border_active()
        } else {
            style_border()
        })
        .title(title_text);

    let list_widget = List::new(items).block(list_block);
    f.render_widget(list_widget, chunks[1]);
}
