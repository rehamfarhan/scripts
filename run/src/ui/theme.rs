#![allow(dead_code)]
use ratatui::style::{Color, Modifier, Style};
use ratatui::widgets::BorderType;

pub const BORDER_TYPE: BorderType = BorderType::Rounded;

pub const COLOR_CYAN: Color = Color::Rgb(0, 240, 255);
pub const COLOR_GREEN: Color = Color::Rgb(57, 255, 20);
pub const COLOR_YELLOW: Color = Color::Rgb(255, 183, 0);
pub const COLOR_RED: Color = Color::Rgb(255, 60, 60);
pub const COLOR_PURPLE: Color = Color::Rgb(180, 100, 255);
pub const COLOR_GREY: Color = Color::Rgb(120, 130, 140);
pub const COLOR_DARK_GREY: Color = Color::Rgb(60, 68, 76);
pub const COLOR_BG_PANEL: Color = Color::Rgb(18, 22, 28);
pub const COLOR_BG_POPUP: Color = Color::Rgb(24, 28, 36);

pub fn style_title() -> Style {
    Style::default()
        .fg(COLOR_CYAN)
        .add_modifier(Modifier::BOLD)
}

pub fn style_header() -> Style {
    Style::default()
        .fg(COLOR_YELLOW)
        .add_modifier(Modifier::BOLD)
}

pub fn style_border() -> Style {
    Style::default().fg(COLOR_DARK_GREY)
}

pub fn style_border_active() -> Style {
    Style::default().fg(COLOR_CYAN)
}

pub fn style_item_normal() -> Style {
    Style::default().fg(Color::White)
}

pub fn style_item_selected() -> Style {
    Style::default()
        .fg(COLOR_CYAN)
        .bg(Color::Rgb(30, 42, 56))
        .add_modifier(Modifier::BOLD)
}

pub fn style_meta_label() -> Style {
    Style::default()
        .fg(COLOR_GREY)
        .add_modifier(Modifier::BOLD)
}

pub fn style_meta_val() -> Style {
    Style::default().fg(Color::White)
}

pub fn style_keybind() -> Style {
    Style::default()
        .fg(COLOR_YELLOW)
        .add_modifier(Modifier::BOLD)
}

pub fn style_tip() -> Style {
    Style::default().fg(COLOR_PURPLE)
}
