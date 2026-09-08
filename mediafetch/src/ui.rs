use crate::downloader::DownloadSummary;
use crate::metadata::MediaMetadata;
use crate::presets::PresetType;
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{
        Block, BorderType, Borders, Clear, Gauge, List, ListItem, Paragraph, Wrap,
    },
    Frame,
};

#[allow(dead_code)]
pub struct AppState {
    pub url: String,
    pub input_mode: bool,
    pub input_buffer: String,
    pub selected_preset_idx: usize,
    pub metadata: Option<MediaMetadata>,
    pub resolving: bool,
    pub downloading: bool,
    pub download_percent: f64,
    pub download_speed: String,
    pub download_eta: String,
    pub download_size: String,
    pub current_step: String,
    pub error_message: Option<String>,
    pub completed_summary: Option<DownloadSummary>,
}

impl AppState {
    pub fn new(url: String, preselected_preset: Option<PresetType>) -> Self {
        let selected_preset_idx = preselected_preset
            .and_then(|p| PresetType::ALL.iter().position(|&x| x == p))
            .unwrap_or(0);

        let input_mode = url.trim().is_empty();

        Self {
            url,
            input_mode,
            input_buffer: String::new(),
            selected_preset_idx,
            metadata: None,
            resolving: false,
            downloading: false,
            download_percent: 0.0,
            download_speed: "-- KiB/s".to_string(),
            download_eta: "--:--".to_string(),
            download_size: "-- MiB".to_string(),
            current_step: "Ready".to_string(),
            error_message: None,
            completed_summary: None,
        }
    }

    pub fn selected_preset(&self) -> PresetType {
        PresetType::ALL[self.selected_preset_idx]
    }

    pub fn next_preset(&mut self) {
        if self.selected_preset_idx + 1 < PresetType::ALL.len() {
            self.selected_preset_idx += 1;
        } else {
            self.selected_preset_idx = 0;
        }
    }

    pub fn prev_preset(&mut self) {
        if self.selected_preset_idx > 0 {
            self.selected_preset_idx -= 1;
        } else {
            self.selected_preset_idx = PresetType::ALL.len() - 1;
        }
    }

    pub fn set_preset_by_idx(&mut self, idx: usize) {
        if idx < PresetType::ALL.len() {
            self.selected_preset_idx = idx;
        }
    }
}

pub fn render(f: &mut Frame, app: &AppState) {
    let size = f.area();

    // Main layout: Header (6 lines), Middle (expand), Progress & Footer (7 lines)
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(6), // Header
            Constraint::Min(10),   // Middle (Presets + Details)
            Constraint::Length(6), // Progress & Status
            Constraint::Length(1), // Footer keys
        ])
        .split(size);

    render_header(f, app, chunks[0]);
    render_middle(f, app, chunks[1]);
    render_progress(f, app, chunks[2]);
    render_footer(f, app, chunks[3]);

    if app.input_mode {
        render_input_modal(f, app, size);
    }
}

fn render_header(f: &mut Frame, app: &AppState, area: Rect) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Cyan))
        .title(Span::styled(" 📥 MEDIAFETCH ", Style::default().fg(Color::Black).bg(Color::Cyan).add_modifier(Modifier::BOLD)));

    let mut lines = Vec::new();

    if let Some(ref meta) = app.metadata {
        let title_line = Line::from(vec![
            Span::styled("🎬 ", Style::default()),
            Span::styled(meta.display_title(), Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
        ]);

        let meta_line = Line::from(vec![
            Span::styled("👤 ", Style::default()),
            Span::styled(meta.display_uploader(), Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)),
            Span::styled("   ⏱️  ", Style::default()),
            Span::styled(meta.formatted_duration(), Style::default().fg(Color::Magenta)),
            Span::styled("   👁️  ", Style::default()),
            Span::styled(meta.formatted_views(), Style::default().fg(Color::Green)),
            Span::styled("   📅 ", Style::default()),
            Span::styled(meta.formatted_date(), Style::default().fg(Color::DarkGray)),
        ]);

        lines.push(title_line);
        lines.push(meta_line);
    } else if app.resolving {
        lines.push(Line::from(vec![
            Span::styled("⚡ Resolving media stream & metadata...", Style::default().fg(Color::Yellow).add_modifier(Modifier::ITALIC)),
        ]));
        lines.push(Line::from(vec![
            Span::styled("🔗 URL: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&app.url, Style::default().fg(Color::Cyan)),
        ]));
    } else if !app.url.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("🔗 Ready to inspect: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&app.url, Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
        ]));
        lines.push(Line::from(vec![
            Span::styled("Press [Enter] to fetch or change preset below", Style::default().fg(Color::Gray)),
        ]));
    } else {
        lines.push(Line::from(vec![
            Span::styled("No URL provided. Press 'u' to enter URL or copy a YouTube link.", Style::default().fg(Color::DarkGray)),
        ]));
    }

    let p = Paragraph::new(lines).block(block);
    f.render_widget(p, area);
}

fn render_middle(f: &mut Frame, app: &AppState, area: Rect) {
    let split = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(45), Constraint::Percentage(55)])
        .split(area);

    render_presets_list(f, app, split[0]);
    render_inspector(f, app, split[1]);
}

fn render_presets_list(f: &mut Frame, app: &AppState, area: Rect) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Blue))
        .title(" 🎯 Smart Presets ");

    let items: Vec<ListItem> = PresetType::ALL
        .iter()
        .enumerate()
        .map(|(i, preset)| {
            let is_selected = i == app.selected_preset_idx;
            let num_key = format!("[{}]", i + 1);

            let prefix = if is_selected { " ❯ " } else { "   " };
            let (bg, fg) = if is_selected {
                (Color::Rgb(30, 45, 75), Color::White)
            } else {
                (Color::Reset, Color::Gray)
            };

            let line = Line::from(vec![
                Span::styled(prefix, Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
                Span::styled(format!("{:<4} ", num_key), Style::default().fg(Color::DarkGray)),
                Span::styled(format!("{} ", preset.icon()), Style::default()),
                Span::styled(format!("{:<14}", preset.title()), Style::default().fg(fg).add_modifier(if is_selected { Modifier::BOLD } else { Modifier::empty() })),
                Span::styled(format!("{:>18}", preset.badge()), Style::default().fg(Color::LightBlue)),
            ]);

            ListItem::new(line).style(Style::default().bg(bg))
        })
        .collect();

    let list = List::new(items).block(block);
    f.render_widget(list, area);
}

fn render_inspector(f: &mut Frame, app: &AppState, area: Rect) {
    let preset = app.selected_preset();
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Blue))
        .title(" 🔍 Preset Inspector ");

    let target_dir = preset.target_directory();
    let lyrics_tag = if preset.should_fetch_lyrics() {
        Span::styled("LRCLIB (USLT embedded + .lrc sidecar)", Style::default().fg(Color::Green))
    } else {
        Span::styled("Disabled", Style::default().fg(Color::DarkGray))
    };

    let lines = vec![
        Line::from(vec![
            Span::styled("Preset:       ", Style::default().fg(Color::DarkGray)),
            Span::styled(preset.title(), Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::styled(format!(" ({})", preset.badge()), Style::default().fg(Color::LightBlue)),
        ]),
        Line::from(vec![
            Span::styled("Destination:  ", Style::default().fg(Color::DarkGray)),
            Span::styled(target_dir.to_string_lossy(), Style::default().fg(Color::Yellow)),
        ]),
        Line::from(vec![
            Span::styled("Lyrics Tag:   ", Style::default().fg(Color::DarkGray)),
            lyrics_tag,
        ]),
        Line::from(vec![
            Span::styled("Thumbnails:   ", Style::default().fg(Color::DarkGray)),
            Span::styled("Embedded high-res / square cover", Style::default().fg(Color::LightCyan)),
        ]),
        Line::from(""),
        Line::from(vec![
            Span::styled("Description:  ", Style::default().fg(Color::DarkGray)),
        ]),
        Line::from(vec![
            Span::styled(preset.description(), Style::default().fg(Color::White)),
        ]),
    ];

    let p = Paragraph::new(lines)
        .block(block)
        .wrap(Wrap { trim: true });
    f.render_widget(p, area);
}

fn render_progress(f: &mut Frame, app: &AppState, area: Rect) {
    let border_color = if app.downloading {
        Color::Green
    } else if app.error_message.is_some() {
        Color::Red
    } else {
        Color::DarkGray
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(border_color))
        .title(" ⚡ Status & Progress ");

    let inner = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Length(2), Constraint::Length(1)])
        .margin(1)
        .split(area);

    f.render_widget(block, area);

    // Status message line
    let status_text = if let Some(ref err) = app.error_message {
        Line::from(vec![
            Span::styled("❌ Error: ", Style::default().fg(Color::Red).add_modifier(Modifier::BOLD)),
            Span::styled(err, Style::default().fg(Color::LightRed)),
        ])
    } else if app.downloading {
        Line::from(vec![
            Span::styled("⬇ ", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
            Span::styled(&app.current_step, Style::default().fg(Color::White)),
            Span::styled("   Speed: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&app.download_speed, Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::styled("   ETA: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&app.download_eta, Style::default().fg(Color::Yellow)),
            Span::styled("   Size: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&app.download_size, Style::default().fg(Color::Magenta)),
        ])
    } else {
        Line::from(vec![
            Span::styled("Status: ", Style::default().fg(Color::DarkGray)),
            Span::styled(&app.current_step, Style::default().fg(Color::Gray)),
        ])
    };

    f.render_widget(Paragraph::new(status_text), inner[0]);

    // Gauge bar
    let gauge_ratio = (app.download_percent / 100.0).clamp(0.0, 1.0);
    let gauge_label = format!("{:.1}%", app.download_percent);
    let gauge = Gauge::default()
        .gauge_style(Style::default().fg(Color::Cyan).bg(Color::Rgb(25, 30, 45)))
        .ratio(gauge_ratio)
        .label(gauge_label);

    f.render_widget(gauge, inner[1]);
}

fn render_footer(f: &mut Frame, _app: &AppState, area: Rect) {
    let keys = Line::from(vec![
        Span::styled(" [Enter] ", Style::default().fg(Color::Black).bg(Color::Cyan).add_modifier(Modifier::BOLD)),
        Span::styled(" Download   ", Style::default().fg(Color::White)),
        Span::styled(" [1-6] ", Style::default().fg(Color::Black).bg(Color::LightBlue).add_modifier(Modifier::BOLD)),
        Span::styled(" Select Preset   ", Style::default().fg(Color::White)),
        Span::styled(" [j/k/↑/↓] ", Style::default().fg(Color::Black).bg(Color::DarkGray).add_modifier(Modifier::BOLD)),
        Span::styled(" Navigate   ", Style::default().fg(Color::White)),
        Span::styled(" [u] ", Style::default().fg(Color::Black).bg(Color::Yellow).add_modifier(Modifier::BOLD)),
        Span::styled(" Paste/Edit URL   ", Style::default().fg(Color::White)),
        Span::styled(" [q/Esc] ", Style::default().fg(Color::Black).bg(Color::Red).add_modifier(Modifier::BOLD)),
        Span::styled(" Quit", Style::default().fg(Color::White)),
    ]);

    let p = Paragraph::new(keys).alignment(Alignment::Center);
    f.render_widget(p, area);
}

fn render_input_modal(f: &mut Frame, app: &AppState, area: Rect) {
    let modal_width = 70.min(area.width.saturating_sub(4));
    let modal_height = 8.min(area.height.saturating_sub(4));

    let x = (area.width.saturating_sub(modal_width)) / 2;
    let y = (area.height.saturating_sub(modal_height)) / 2;
    let modal_area = Rect::new(x, y, modal_width, modal_height);

    f.render_widget(Clear, modal_area);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Cyan))
        .title(" 🔗 Enter Media URL or Search Query ");

    let inner = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(1), Constraint::Length(3), Constraint::Length(1)])
        .margin(1)
        .split(modal_area);

    f.render_widget(block, modal_area);

    let prompt = Paragraph::new("Paste YouTube / media URL and press [Enter]:")
        .style(Style::default().fg(Color::DarkGray));
    f.render_widget(prompt, inner[0]);

    let input_block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Yellow));

    let input = Paragraph::new(app.input_buffer.as_str())
        .block(input_block)
        .style(Style::default().fg(Color::White));
    f.render_widget(input, inner[1]);

    let help = Paragraph::new("[Enter] Confirm   |   [Esc] Cancel")
        .style(Style::default().fg(Color::DarkGray))
        .alignment(Alignment::Right);
    f.render_widget(help, inner[2]);
}
