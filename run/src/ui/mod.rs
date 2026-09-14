pub mod app;
pub mod events;
pub mod layout;
pub mod theme;
pub mod widgets;

use crossterm::cursor::Show;
use crossterm::event::{self, Event};
use crossterm::execute;
use crossterm::terminal::{
    disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen,
};
use ratatui::backend::CrosstermBackend;
use ratatui::style::Style;
use ratatui::widgets::{Block, Borders, Paragraph};
use ratatui::Terminal;
use std::io::{self, stdout};
use std::path::PathBuf;
use std::time::Duration;

use crate::config::main_title;
use crate::launcher::launch_game_attached;
use crate::ui::app::App;
use crate::ui::events::handle_key_event;
use crate::ui::layout::DashboardLayout;
use crate::ui::theme::{style_title, BORDER_TYPE, COLOR_DARK_GREY};
use crate::ui::widgets::game_list::render_game_list;
use crate::ui::widgets::hotkeys::render_hotkeys;
use crate::ui::widgets::inspector::render_inspector;
use crate::ui::widgets::modals::render_modals;

pub fn run_tui(games_root: PathBuf) -> io::Result<()> {
    enable_raw_mode()?;
    let mut stdout = stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut app = App::new(games_root);

    // Set panic hook to ensure terminal is restored
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let _ = disable_raw_mode();
        let _ = execute!(std::io::stdout(), LeaveAlternateScreen, Show);
        default_hook(info);
    }));

    while !app.should_quit {
        terminal.draw(|f| {
            let layout = DashboardLayout::new(f.area());

            // 1. Header Bar
            let title_text = main_title();
            let header_block = Block::default()
                .borders(Borders::ALL)
                .border_type(BORDER_TYPE)
                .border_style(Style::default().fg(COLOR_DARK_GREY));
            let header_widget = Paragraph::new(format!("  {}", title_text))
                .style(style_title())
                .block(header_block);
            f.render_widget(header_widget, layout.header);

            // 2. Left Game Library List
            render_game_list(f, &app, layout.left_library);

            // 3. Right Top Inspector
            render_inspector(f, &app, layout.right_inspector);

            // 4. Right Bottom Hotkeys & Tips
            render_hotkeys(f, &app, layout.right_hotkeys);

            // 5. Active Modals (Overlay)
            render_modals(f, &app, f.area());
        })?;

        // Handle external editor launch cleanly
        if let Some(script_path) = app.needs_editor.take() {
            let editor = std::env::var("EDITOR").unwrap_or_else(|_| "nvim".to_string());
            let _ = disable_raw_mode();
            let _ = execute!(std::io::stdout(), LeaveAlternateScreen, Show);
            let _ = std::process::Command::new(&editor).arg(&script_path).status();
            let _ = execute!(std::io::stdout(), EnterAlternateScreen);
            let _ = enable_raw_mode();
            terminal.clear()?;
            app.set_toast("✓ Wrapper script saved");
            app.reload_games();
            continue;
        }

        // Check if a game was requested to launch
        if let Some(game) = app.launch_target.take() {
            // Restore terminal before running game
            let _ = disable_raw_mode();
            let _ = execute!(std::io::stdout(), LeaveAlternateScreen, Show);

            let _ = launch_game_attached(&app.games_root, &game, true);

            // Re-enter TUI and force a full redraw
            let _ = execute!(std::io::stdout(), EnterAlternateScreen);
            let _ = enable_raw_mode();
            terminal.clear()?;
            app.reload_games();
            continue;
        }

        if event::poll(Duration::from_millis(50))? {
            if let Event::Key(key) = event::read()? {
                if key.kind == crossterm::event::KeyEventKind::Press {
                    handle_key_event(&mut app, key);
                }
            }
        }
    }

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, Show)?;
    terminal.show_cursor()?;

    Ok(())
}
