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

    // 2. Game List with viewport windowing
    let list_height = chunks[1].height.saturating_sub(2) as usize;
    let visible_count = list_height.max(1);
    let total_items = app.filtered_indices.len();

    let offset = if app.selected_index < visible_count {
        0
    } else {
        app.selected_index + 1 - visible_count
    };
    let end = (offset + visible_count).min(total_items);
    let visible_slice = if total_items > 0 && offset < total_items {
        &app.filtered_indices[offset..end]
    } else {
        &[]
    };

    let items: Vec<ListItem> = visible_slice
        .iter()
        .enumerate()
        .map(|(rel_idx, &game_idx)| {
            let actual_idx = offset + rel_idx;
            let game = &app.all_games[game_idx];
            let is_selected = actual_idx == app.selected_index;

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

            let fav_prefix = if game.favorite { "⭐ " } else { "" };

            let line = Line::from(vec![
                Span::styled(
                    prefix,
                    if is_selected {
                        Style::default().fg(COLOR_CYAN)
                    } else {
                        Style::default().fg(COLOR_DARK_GREY)
                    },
                ),
                Span::raw(format!("{}{} ", fav_prefix, icon)),
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
    let scroll_hint = if filtered_count > visible_count {
        let up = if offset > 0 { "▲" } else { " " };
        let down = if end < filtered_count { "▼" } else { " " };
        format!(" {} {} ", up, down)
    } else {
        String::new()
    };

    let sort_badge = format!("[{}]", app.sort_mode.label());
    let title_text = if app.search_query.is_empty() {
        format!(" Games ({}) {} {} ", total_count, sort_badge, scroll_hint)
    } else {
        format!(" Games ({}/{}) {} {} ", filtered_count, total_count, sort_badge, scroll_hint)
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
