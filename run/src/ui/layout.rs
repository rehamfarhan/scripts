use ratatui::layout::{Constraint, Direction, Layout, Rect};

pub struct DashboardLayout {
    pub header: Rect,
    pub left_library: Rect,
    pub right_inspector: Rect,
    pub right_hotkeys: Rect,
}

impl DashboardLayout {
    pub fn new(area: Rect, show_hotkeys: bool) -> Self {
        // Main vertical split: Title bar (3 rows) and content area
        let main_chunks = Layout::default()
            .direction(Direction::Vertical)
            .constraints([Constraint::Length(3), Constraint::Min(10)])
            .split(area);

        // Horizontal split: Left (35%) and Right (65%)
        let content_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(35), Constraint::Percentage(65)])
            .split(main_chunks[1]);

        if show_hotkeys {
            // Right pane vertical split: Inspector (72%) and Hotkeys/Tips (28%)
            let right_chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([Constraint::Percentage(72), Constraint::Percentage(28)])
                .split(content_chunks[1]);

            Self {
                header: main_chunks[0],
                left_library: content_chunks[0],
                right_inspector: right_chunks[0],
                right_hotkeys: right_chunks[1],
            }
        } else {
            Self {
                header: main_chunks[0],
                left_library: content_chunks[0],
                right_inspector: content_chunks[1],
                right_hotkeys: Rect::default(),
            }
        }
    }
}
