use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use fuzzy_matcher::skim::SkimMatcherV2;
use fuzzy_matcher::FuzzyMatcher;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::db::GameRecord;
use crate::model::{format_star_rating, WineOpts};
use crate::scanner::{create_desktop_entry, create_launcher_script, scan_executables, ScriptGenerationResult};
use crate::ui::app::{ActiveModal, App};

pub fn handle_key_event(app: &mut App, key: KeyEvent) {
    // 1. Handle Active Modals
    if !matches!(app.active_modal, ActiveModal::None) {
        handle_modal_key(app, key);
        return;
    }

    // 2. Handle Search Bar Input Mode
    if app.is_searching {
        if key.modifiers.contains(KeyModifiers::CONTROL) {
            match key.code {
                KeyCode::Char('j') | KeyCode::Char('n') => {
                    app.select_next();
                    return;
                }
                KeyCode::Char('k') | KeyCode::Char('p') => {
                    app.select_prev();
                    return;
                }
                KeyCode::Char('d') => {
                    app.scroll_down(8);
                    return;
                }
                KeyCode::Char('u') => {
                    app.search_query.clear();
                    app.apply_filter();
                    return;
                }
                KeyCode::Char('w') => {
                    let trimmed = app.search_query.trim_end();
                    if let Some(idx) = trimmed.rfind(' ') {
                        app.search_query.truncate(idx + 1);
                    } else {
                        app.search_query.clear();
                    }
                    app.apply_filter();
                    return;
                }
                _ => {}
            }
        }

        match key.code {
            KeyCode::Esc => {
                app.is_searching = false;
            }
            KeyCode::Enter => {
                if let Some(game) = app.selected_game().cloned() {
                    app.launch_target = Some(game);
                }
            }
            KeyCode::Up => {
                app.select_prev();
            }
            KeyCode::Down => {
                app.select_next();
            }
            KeyCode::PageUp => {
                app.scroll_up(8);
            }
            KeyCode::PageDown => {
                app.scroll_down(8);
            }
            KeyCode::Home => {
                app.select_first();
            }
            KeyCode::End => {
                app.select_last();
            }
            KeyCode::Backspace => {
                app.search_query.pop();
                app.apply_filter();
            }
            KeyCode::Char(c) => {
                app.search_query.push(c);
                app.apply_filter();
            }
            _ => {}
        }
        return;
    }

    // 3. Main Dashboard Navigation & Hotkeys
    if key.modifiers.contains(KeyModifiers::CONTROL) {
        match key.code {
            KeyCode::Char('d') => {
                app.scroll_down(8);
                return;
            }
            KeyCode::Char('u') => {
                app.scroll_up(8);
                return;
            }
            KeyCode::Char('j') | KeyCode::Char('n') => {
                app.select_next();
                return;
            }
            KeyCode::Char('k') | KeyCode::Char('p') => {
                app.select_prev();
                return;
            }
            KeyCode::Char('r') => {
                if let Some(game) = app.selected_game() {
                    app.active_modal = ActiveModal::ResetScriptConfirmation {
                        game_name: game.display_name.clone(),
                    };
                }
                return;
            }
            _ => {}
        }
    }

    match key.code {
        KeyCode::Char('q') => {
            app.should_quit = true;
        }
        KeyCode::Esc => {
            if !app.search_query.is_empty() {
                app.search_query.clear();
                app.apply_filter();
            } else {
                app.should_quit = true;
            }
        }
        KeyCode::Char('/') => {
            app.is_searching = true;
        }
        KeyCode::Char('i') => {
            app.show_quick_actions = !app.show_quick_actions;
        }
        // Vim Navigation
        KeyCode::Char('j') | KeyCode::Down => {
            app.select_next();
        }
        KeyCode::Char('k') | KeyCode::Up => {
            app.select_prev();
        }
        KeyCode::Char('g') | KeyCode::Home => {
            app.select_first();
        }
        KeyCode::Char('G') | KeyCode::End => {
            app.select_last();
        }
        KeyCode::PageDown => {
            app.scroll_down(8);
        }
        KeyCode::PageUp => {
            app.scroll_up(8);
        }
        KeyCode::Enter => {
            if let Some(game) = app.selected_game().cloned() {
                app.launch_target = Some(game);
            }
        }
        // Sorting: s = next sort field, S (Shift+S) = toggle ascending/descending order
        KeyCode::Char('s') => {
            if key.modifiers.contains(KeyModifiers::SHIFT) {
                app.sort_descending = !app.sort_descending;
            } else {
                app.sort_field = app.sort_field.next();
            }
            app.reload_games();
            app.set_toast(format!("🔀 Sort: {}", app.sort_label()));
        }
        KeyCode::Char('S') => {
            app.sort_descending = !app.sort_descending;
            app.reload_games();
            app.set_toast(format!("🔀 Sort: {}", app.sort_label()));
        }
        // Favorite toggle
        KeyCode::Char('f') => {
            if let Some(game) = app.selected_game().cloned() {
                if let Ok(is_fav) = app.db.toggle_favorite(&game.dir) {
                    app.reload_games();
                    if is_fav {
                        app.set_toast(format!("⭐ Pinned '{}' to Favorites", game.display_name));
                    } else {
                        app.set_toast(format!("Unpinned '{}' from Favorites", game.display_name));
                    }
                }
            }
        }
        KeyCode::Char('r') => {
            if let Some(game) = app.selected_game() {
                let current_rating = game.rating.min(10);
                let opt_idx = if current_rating == 0 {
                    10
                } else {
                    10 - (current_rating as usize)
                };

                app.active_modal = ActiveModal::RateGame {
                    selected_opt: opt_idx,
                };
            }
        }
        // Keyboard Patch (keyd) remapped to 'p' / 'P' to free 'k' for Vim Up
        KeyCode::Char('p') | KeyCode::Char('P') => {
            if let Some(game) = app.selected_game() {
                let current_remap = game
                    .wine_opts
                    .as_ref()
                    .and_then(|o| o.keyd_remap.as_deref())
                    .unwrap_or("");

                let opt_idx = if current_remap == "leftshift=leftcontrol" {
                    1
                } else if !current_remap.is_empty() {
                    2
                } else {
                    0
                };

                app.active_modal = ActiveModal::KeyboardPatch {
                    selected_opt: opt_idx,
                    custom_input: current_remap.to_string(),
                    is_custom_mode: false,
                };
            }
        }
        KeyCode::Char('c') => {
            if let Some(game) = app.selected_game() {
                let opts = game.wine_opts.clone().unwrap_or_default();
                app.active_modal = ActiveModal::ExecutionSettings {
                    selected_opt: 0,
                    is_windows: game.is_windows,
                    opts,
                };
            }
        }
        KeyCode::Char('e') => {
            if let Some(game) = app.selected_game().cloned() {
                let folder_path = app.games_root.join(&game.dir);
                let binary_path = PathBuf::from(&game.binary);
                let wine_prefix = game.wine_prefix.as_ref().map(PathBuf::from);

                let result = create_launcher_script(
                    &folder_path,
                    &binary_path,
                    &game.display_name,
                    game.is_windows,
                    wine_prefix.as_deref(),
                    game.wine_opts.as_ref(),
                );

                if let Ok((script, _gen)) = result {
                    let mut updated = game.clone();
                    updated.custom_wrapper = true;
                    let _ = app.db.upsert_game(&updated);

                    // Delegate editor spawning to main loop to ensure clean terminal teardown & redraw!
                    app.needs_editor = Some(script);
                }
            }
        }
        KeyCode::Char('d') => {
            if let Some(game) = app.selected_game().cloned() {
                let folder_path = app.games_root.join(&game.dir);
                let launcher = folder_path.join("start_game.sh");
                if launcher.is_file() {
                    match create_desktop_entry(&game.display_name, &launcher) {
                        Ok(p) => {
                            let mut updated = game.clone();
                            updated.desktop_entry = Some(p.to_string_lossy().to_string());
                            let _ = app.db.upsert_game(&updated);
                            app.set_toast(format!("✓ Desktop shortcut created for '{}'", game.display_name));
                        }
                        Err(e) => app.set_toast(format!("✗ Failed to create shortcut: {}", e)),
                    }
                }
            }
        }
        KeyCode::Char('o') => {
            if let Some(game) = app.selected_game() {
                let folder_path = app.games_root.join(&game.dir);
                let fm = if which_bin("spf") { "spf" } else { "xdg-open" };
                let _ = Command::new(fm).arg(&folder_path).spawn();
                app.set_toast(format!("📁 Opened folder '{}'", game.dir));
            }
        }
        KeyCode::Char('m') => {
            if let Some(game) = app.selected_game() {
                let folder_path = app.games_root.join(&game.dir);
                let binaries = scan_executables(&folder_path, 2);
                if !binaries.is_empty() {
                    let filtered_indices: Vec<usize> = (0..binaries.len()).collect();
                    app.active_modal = ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin: 0,
                        search_query: String::new(),
                    };
                } else {
                    app.set_toast("✗ No executables found in folder");
                }
            }
        }
        KeyCode::Char('n') => {
            if let Some(game) = app.selected_game() {
                app.active_modal = ActiveModal::RenameGame {
                    input: game.display_name.clone(),
                };
            }
        }
        KeyCode::Delete | KeyCode::Char('x') => {
            if let Some(game) = app.selected_game().cloned() {
                let _ = app.db.remove_game(&game.dir);
                app.reload_games();
                app.set_toast(format!("🗑️ Removed '{}' (Stats preserved in DB)", game.display_name));
            }
        }
        _ => {}
    }
}

fn filter_binary_indices(binaries: &[PathBuf], game_dir: &Path, query: &str) -> Vec<usize> {
    if query.trim().is_empty() {
        return (0..binaries.len()).collect();
    }
    let matcher = SkimMatcherV2::default();
    let mut scored = Vec::new();
    for (idx, bin) in binaries.iter().enumerate() {
        let rel = bin.strip_prefix(game_dir).unwrap_or(bin).to_string_lossy();
        if let Some(score) = matcher.fuzzy_match(&rel, query) {
            scored.push((idx, score));
        }
    }
    scored.sort_by(|a, b| b.1.cmp(&a.1));
    scored.into_iter().map(|(idx, _)| idx).collect()
}

fn handle_modal_key(app: &mut App, key: KeyEvent) {
    let modal = std::mem::replace(&mut app.active_modal, ActiveModal::None);
    let next_modal = match modal {
        ActiveModal::RateGame { mut selected_opt } => match key.code {
            KeyCode::Esc | KeyCode::Char('q') => ActiveModal::None,
            KeyCode::Char('k') | KeyCode::Up => {
                if selected_opt > 0 {
                    selected_opt -= 1;
                } else {
                    selected_opt = 10;
                }
                ActiveModal::RateGame { selected_opt }
            }
            KeyCode::Char('j') | KeyCode::Down => {
                selected_opt = (selected_opt + 1) % 11;
                ActiveModal::RateGame { selected_opt }
            }
            KeyCode::Char('g') | KeyCode::Home => {
                ActiveModal::RateGame { selected_opt: 0 }
            }
            KeyCode::Char('G') | KeyCode::End => {
                ActiveModal::RateGame { selected_opt: 10 }
            }
            KeyCode::Enter => {
                let chosen_rating = (10 - selected_opt.min(10)) as u8;
                if let Some(game) = app.selected_game().cloned() {
                    let _ = app.db.set_rating(&game.dir, chosen_rating);
                    app.reload_games();
                    app.set_toast(format!("✓ Rated '{}': {}", game.display_name, format_star_rating(chosen_rating)));
                }
                ActiveModal::None
            }
            _ => ActiveModal::RateGame { selected_opt },
        },
        ActiveModal::KeyboardPatch {
            mut selected_opt,
            mut custom_input,
            mut is_custom_mode,
        } => {
            if is_custom_mode {
                match key.code {
                    KeyCode::Esc => {
                        is_custom_mode = false;
                        ActiveModal::KeyboardPatch {
                            selected_opt,
                            custom_input,
                            is_custom_mode,
                        }
                    }
                    KeyCode::Backspace => {
                        custom_input.pop();
                        ActiveModal::KeyboardPatch {
                            selected_opt,
                            custom_input,
                            is_custom_mode,
                        }
                    }
                    KeyCode::Char(c) => {
                        custom_input.push(c);
                        ActiveModal::KeyboardPatch {
                            selected_opt,
                            custom_input,
                            is_custom_mode,
                        }
                    }
                    KeyCode::Enter => {
                        let trimmed = custom_input.trim();
                        if trimmed.is_empty() {
                            apply_keyd_patch(app, None);
                        } else {
                            apply_keyd_patch(app, Some(trimmed.to_string()));
                        }
                        ActiveModal::None
                    }
                    _ => ActiveModal::KeyboardPatch {
                        selected_opt,
                        custom_input,
                        is_custom_mode,
                    },
                }
            } else {
                match key.code {
                    KeyCode::Esc | KeyCode::Char('q') => ActiveModal::None,
                    KeyCode::Char('k') | KeyCode::Up => {
                        if selected_opt > 0 {
                            selected_opt -= 1;
                        } else {
                            selected_opt = 2;
                        }
                        ActiveModal::KeyboardPatch {
                            selected_opt,
                            custom_input,
                            is_custom_mode,
                        }
                    }
                    KeyCode::Char('j') | KeyCode::Down => {
                        selected_opt = (selected_opt + 1) % 3;
                        ActiveModal::KeyboardPatch {
                            selected_opt,
                            custom_input,
                            is_custom_mode,
                        }
                    }
                    KeyCode::Char('g') | KeyCode::Home => {
                        ActiveModal::KeyboardPatch {
                            selected_opt: 0,
                            custom_input,
                            is_custom_mode,
                        }
                    }
                    KeyCode::Char('G') | KeyCode::End => {
                        ActiveModal::KeyboardPatch {
                            selected_opt: 2,
                            custom_input,
                            is_custom_mode,
                        }
                    }
                    KeyCode::Enter => match selected_opt {
                        0 => {
                            apply_keyd_patch(app, None);
                            ActiveModal::None
                        }
                        1 => {
                            apply_keyd_patch(app, Some("leftshift=leftcontrol".to_string()));
                            ActiveModal::None
                        }
                        2 => {
                            is_custom_mode = true;
                            ActiveModal::KeyboardPatch {
                                selected_opt,
                                custom_input,
                                is_custom_mode,
                            }
                        }
                        _ => ActiveModal::None,
                    },
                    _ => ActiveModal::KeyboardPatch {
                        selected_opt,
                        custom_input,
                        is_custom_mode,
                    },
                }
            }
        }
        ActiveModal::ExecutionSettings {
            mut selected_opt,
            is_windows,
            mut opts,
        } => {
            if !is_windows {
                match key.code {
                    KeyCode::Esc | KeyCode::Char('q') => ActiveModal::None,
                    KeyCode::Char('k') | KeyCode::Up => {
                        if selected_opt > 0 {
                            selected_opt -= 1;
                        } else {
                            selected_opt = 2;
                        }
                        ActiveModal::ExecutionSettings {
                            selected_opt,
                            is_windows,
                            opts,
                        }
                    }
                    KeyCode::Char('j') | KeyCode::Down => {
                        selected_opt = (selected_opt + 1) % 3;
                        ActiveModal::ExecutionSettings {
                            selected_opt,
                            is_windows,
                            opts,
                        }
                    }
                    KeyCode::Char('g') | KeyCode::Home => {
                        ActiveModal::ExecutionSettings {
                            selected_opt: 0,
                            is_windows,
                            opts,
                        }
                    }
                    KeyCode::Char('G') | KeyCode::End => {
                        ActiveModal::ExecutionSettings {
                            selected_opt: 2,
                            is_windows,
                            opts,
                        }
                    }
                    KeyCode::Enter | KeyCode::Char(' ') | KeyCode::Char('l') => {
                        match selected_opt {
                            0 => opts.sdl_driver = None,
                            1 => opts.sdl_driver = Some("x11".to_string()),
                            2 => opts.sdl_driver = Some("wayland".to_string()),
                            _ => {}
                        }
                        if let Some(game) = app.selected_game().cloned() {
                            let mut updated = game.clone();
                            updated.wine_opts = Some(opts.clone());
                            let _ = app.db.upsert_game(&updated);

                            let folder = app.games_root.join(&game.dir);
                            match create_launcher_script(
                                &folder,
                                Path::new(&game.binary),
                                &game.display_name,
                                game.is_windows,
                                game.wine_prefix.as_deref().map(Path::new),
                                Some(&opts),
                            ) {
                                Ok((_, ScriptGenerationResult::SkippedCorruptMarkers)) => {
                                    app.set_toast(format!(
                                        "⚠️ Settings not applied — start_game.sh markers are missing or corrupted for '{}'. Use Ctrl+R to reset the script.",
                                        game.display_name
                                    ));
                                }
                                _ => {
                                    app.set_toast(format!("✓ Video driver updated for '{}'", game.display_name));
                                }
                            }
                            app.reload_games();
                        }
                        ActiveModal::None
                    }
                    _ => ActiveModal::ExecutionSettings {
                        selected_opt,
                        is_windows,
                        opts,
                    },
                }
            } else {
                // Windows games: 3 categories (0..=2), one row per category, with the
                // selected row's value cycled in-place on Enter/Space/'l'. The modal
                // stays open so the user can cycle multiple options before Esc.
                // NOTE: win_ver and sdl_driver for Windows games are stored but not yet
                // consumed by the generated start_game.sh — they are inert placeholders
                // for future Wine integration. See WineOpts doc comments in model.rs.
                match key.code {
                    KeyCode::Esc | KeyCode::Char('q') => ActiveModal::None,
                    KeyCode::Char('k') | KeyCode::Up => {
                        if selected_opt > 0 {
                            selected_opt -= 1;
                        } else {
                            selected_opt = 2;
                        }
                        ActiveModal::ExecutionSettings {
                            selected_opt,
                            is_windows,
                            opts,
                        }
                    }
                    KeyCode::Char('j') | KeyCode::Down => {
                        selected_opt = (selected_opt + 1) % 3;
                        ActiveModal::ExecutionSettings {
                            selected_opt,
                            is_windows,
                            opts,
                        }
                    }
                    KeyCode::Char('g') | KeyCode::Home => {
                        ActiveModal::ExecutionSettings {
                            selected_opt: 0,
                            is_windows,
                            opts,
                        }
                    }
                    KeyCode::Char('G') | KeyCode::End => {
                        ActiveModal::ExecutionSettings {
                            selected_opt: 2,
                            is_windows,
                            opts,
                        }
                    }
                    KeyCode::Enter | KeyCode::Char(' ') | KeyCode::Char('l') => {
                        match selected_opt {
                            // Virtual Desktop Resolution: Native -> 1920x1080 -> 1280x720 -> Native
                            0 => {
                                opts.resolution = match opts.resolution.as_deref() {
                                    None => Some("1920x1080".to_string()),
                                    Some("1920x1080") => Some("1280x720".to_string()),
                                    _ => None,
                                }
                            }
                            // DXVK Performance HUD: Off -> fps -> full -> Off
                            1 => {
                                opts.dxvk_hud = match opts.dxvk_hud.as_deref() {
                                    None => Some("fps".to_string()),
                                    Some("fps") => Some("full".to_string()),
                                    _ => None,
                                }
                            }
                            // SDL driver is Linux-only; under Wine it's stored but inert.
                            // Toggle Auto <-> x11 for informational purposes only.
                            2 => {
                                if opts.sdl_driver.as_deref() == Some("x11") {
                                    opts.sdl_driver = None;
                                } else {
                                    opts.sdl_driver = Some("x11".to_string());
                                }
                            }
                            _ => {}
                        }
                        if let Some(game) = app.selected_game().cloned() {
                            let mut updated = game.clone();
                            updated.wine_opts = Some(opts.clone());
                            let _ = app.db.upsert_game(&updated);

                            let folder = app.games_root.join(&game.dir);
                            match create_launcher_script(
                                &folder,
                                Path::new(&game.binary),
                                &game.display_name,
                                game.is_windows,
                                game.wine_prefix.as_deref().map(Path::new),
                                Some(&opts),
                            ) {
                                Ok((_, ScriptGenerationResult::SkippedCorruptMarkers)) => {
                                    app.set_toast(format!(
                                        "⚠️ Settings not applied — start_game.sh markers are missing or corrupted for '{}'. Use Ctrl+R to reset the script.",
                                        game.display_name
                                    ));
                                }
                                _ => {
                                    app.set_toast(format!("✓ Compatibility settings saved for '{}'", game.display_name));
                                }
                            }
                            app.reload_games();
                        }
                        // Remain open: cycling applies immediately, user can keep cycling.
                        ActiveModal::ExecutionSettings {
                            selected_opt,
                            is_windows,
                            opts,
                        }
                    }
                    _ => ActiveModal::ExecutionSettings {
                        selected_opt,
                        is_windows,
                        opts,
                    },
                }
            }
        }
        ActiveModal::ChangeBinary {
            binaries,
            mut filtered_indices,
            mut selected_bin,
            mut search_query,
        } => {
            let game_dir = app
                .selected_game()
                .map(|g| app.games_root.join(&g.dir))
                .unwrap_or_else(|| app.games_root.clone());

            if key.modifiers.contains(KeyModifiers::CONTROL) {
                match key.code {
                    KeyCode::Char('j') | KeyCode::Char('n') => {
                        if !filtered_indices.is_empty() {
                            selected_bin = (selected_bin + 1) % filtered_indices.len();
                        }
                    }
                    KeyCode::Char('k') | KeyCode::Char('p') => {
                        if selected_bin > 0 {
                            selected_bin -= 1;
                        } else if !filtered_indices.is_empty() {
                            selected_bin = filtered_indices.len() - 1;
                        }
                    }
                    KeyCode::Char('d') => {
                        if !filtered_indices.is_empty() {
                            selected_bin = (selected_bin + 8).min(filtered_indices.len() - 1);
                        }
                    }
                    KeyCode::Char('u') => {
                        search_query.clear();
                        filtered_indices = filter_binary_indices(&binaries, &game_dir, &search_query);
                        selected_bin = 0;
                    }
                    KeyCode::Char('w') => {
                        let trimmed = search_query.trim_end();
                        if let Some(idx) = trimmed.rfind(' ') {
                            search_query.truncate(idx + 1);
                        } else {
                            search_query.clear();
                        }
                        filtered_indices = filter_binary_indices(&binaries, &game_dir, &search_query);
                        selected_bin = 0;
                    }
                    _ => {}
                }
                ActiveModal::ChangeBinary {
                    binaries,
                    filtered_indices,
                    selected_bin,
                    search_query,
                }
            } else {
                match key.code {
                KeyCode::Esc => ActiveModal::None,
                KeyCode::Up => {
                    if selected_bin > 0 {
                        selected_bin -= 1;
                    } else if !filtered_indices.is_empty() {
                        selected_bin = filtered_indices.len() - 1;
                    }
                    ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin,
                        search_query,
                    }
                }
                KeyCode::Down => {
                    if !filtered_indices.is_empty() {
                        selected_bin = (selected_bin + 1) % filtered_indices.len();
                    }
                    ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin,
                        search_query,
                    }
                }
                KeyCode::PageUp => {
                    selected_bin = selected_bin.saturating_sub(8);
                    ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin,
                        search_query,
                    }
                }
                KeyCode::PageDown => {
                    if !filtered_indices.is_empty() {
                        selected_bin = (selected_bin + 8).min(filtered_indices.len() - 1);
                    }
                    ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin,
                        search_query,
                    }
                }
                KeyCode::Home => {
                    ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin: 0,
                        search_query,
                    }
                }
                KeyCode::End => {
                    let last = filtered_indices.len().saturating_sub(1);
                    ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin: last,
                        search_query,
                    }
                }
                KeyCode::Backspace => {
                    search_query.pop();
                    filtered_indices = filter_binary_indices(&binaries, &game_dir, &search_query);
                    selected_bin = 0;
                    ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin,
                        search_query,
                    }
                }
                KeyCode::Char(c) => {
                    search_query.push(c);
                    filtered_indices = filter_binary_indices(&binaries, &game_dir, &search_query);
                    selected_bin = 0;
                    ActiveModal::ChangeBinary {
                        binaries,
                        filtered_indices,
                        selected_bin,
                        search_query,
                    }
                }
                KeyCode::Enter => {
                    if let Some(&bin_idx) = filtered_indices.get(selected_bin) {
                        if let Some(chosen) = binaries.get(bin_idx).cloned() {
                            if let Some(game) = app.selected_game().cloned() {
                                let folder = app.games_root.join(&game.dir);
                                let rel = chosen.strip_prefix(&folder).unwrap_or(&chosen);
                                let is_windows = rel
                                    .extension()
                                    .and_then(|e| e.to_str())
                                    .map(|e| e.eq_ignore_ascii_case("exe") || e.eq_ignore_ascii_case("bat"))
                                    .unwrap_or(false);

                                let mut updated = game.clone();
                                updated.binary = rel.to_string_lossy().to_string();
                                updated.is_windows = is_windows;
                                updated.icon = Some(if is_windows { "💻".to_string() } else { "🐧".to_string() });

                                let _ = create_launcher_script(
                                    &folder,
                                    rel,
                                    &game.display_name,
                                    is_windows,
                                    game.wine_prefix.as_deref().map(Path::new),
                                    game.wine_opts.as_ref(),
                                );
                                let _ = app.db.upsert_game(&updated);
                                app.set_toast(format!("✓ Main binary set to '{}'", rel.display()));
                            }
                        }
                    }
                    app.reload_games();
                    ActiveModal::None
                }
                _ => ActiveModal::ChangeBinary {
                    binaries,
                    filtered_indices,
                    selected_bin,
                    search_query,
                },
                }
            }
        }
        ActiveModal::RenameGame { mut input } => match key.code {
            KeyCode::Esc => ActiveModal::None,
            KeyCode::Backspace => {
                input.pop();
                ActiveModal::RenameGame { input }
            }
            KeyCode::Char(c) => {
                input.push(c);
                ActiveModal::RenameGame { input }
            }
            KeyCode::Enter => {
                let trimmed = input.trim();
                if !trimmed.is_empty() {
                    if let Some(game) = app.selected_game().cloned() {
                        let mut updated = game.clone();
                        updated.display_name = trimmed.to_string();
                        let folder = app.games_root.join(&game.dir);
                        let _ = create_launcher_script(
                            &folder,
                            Path::new(&game.binary),
                            trimmed,
                            game.is_windows,
                            game.wine_prefix.as_deref().map(Path::new),
                            game.wine_opts.as_ref(),
                        );
                        let _ = app.db.upsert_game(&updated);
                        app.set_toast(format!("✓ Renamed game to '{}'", trimmed));
                    }
                }
                app.reload_games();
                ActiveModal::None
            }
            _ => ActiveModal::RenameGame { input },
        },
        ActiveModal::NewGameWizard {
            folders,
            mut current_idx,
            mut binaries,
            mut filtered_indices,
            mut selected_bin,
            mut search_query,
            mut is_searching,
        } => {
            let current_folder = folders[current_idx].clone();
            let folder_name = current_folder
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();

            if is_searching {
                if key.modifiers.contains(KeyModifiers::CONTROL) {
                    match key.code {
                        KeyCode::Char('j') | KeyCode::Char('n') => {
                            if !filtered_indices.is_empty() {
                                selected_bin = (selected_bin + 1) % filtered_indices.len();
                            }
                        }
                        KeyCode::Char('k') | KeyCode::Char('p') => {
                            if selected_bin > 0 {
                                selected_bin -= 1;
                            } else if !filtered_indices.is_empty() {
                                selected_bin = filtered_indices.len() - 1;
                            }
                        }
                        KeyCode::Char('d') => {
                            if !filtered_indices.is_empty() {
                                selected_bin = (selected_bin + 8).min(filtered_indices.len() - 1);
                            }
                        }
                        KeyCode::Char('u') => {
                            search_query.clear();
                            filtered_indices = filter_binary_indices(&binaries, &current_folder, &search_query);
                            selected_bin = 0;
                        }
                        KeyCode::Char('w') => {
                            let trimmed = search_query.trim_end();
                            if let Some(idx) = trimmed.rfind(' ') {
                                search_query.truncate(idx + 1);
                            } else {
                                search_query.clear();
                            }
                            filtered_indices = filter_binary_indices(&binaries, &current_folder, &search_query);
                            selected_bin = 0;
                        }
                        _ => {}
                    }
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        filtered_indices,
                        selected_bin,
                        search_query,
                        is_searching,
                    }
                } else {
                    match key.code {
                        // Esc switches to selection mode where s/i/arrows/j/k work!
                        KeyCode::Esc => {
                            is_searching = false;
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Up => {
                            if selected_bin > 0 {
                                selected_bin -= 1;
                            } else if !filtered_indices.is_empty() {
                                selected_bin = filtered_indices.len() - 1;
                            }
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Down => {
                            if !filtered_indices.is_empty() {
                                selected_bin = (selected_bin + 1) % filtered_indices.len();
                            }
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::PageUp => {
                            selected_bin = selected_bin.saturating_sub(8);
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::PageDown => {
                            if !filtered_indices.is_empty() {
                                selected_bin = (selected_bin + 8).min(filtered_indices.len() - 1);
                            }
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Backspace => {
                            search_query.pop();
                            filtered_indices = filter_binary_indices(&binaries, &current_folder, &search_query);
                            selected_bin = 0;
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Char(c) => {
                            search_query.push(c);
                            filtered_indices = filter_binary_indices(&binaries, &current_folder, &search_query);
                            selected_bin = 0;
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Enter => {
                            if let Some(&bin_idx) = filtered_indices.get(selected_bin) {
                                if let Some(chosen) = binaries.get(bin_idx).cloned() {
                                    let rel = chosen.strip_prefix(&current_folder).unwrap_or(&chosen);
                                    let is_windows = rel
                                        .extension()
                                        .and_then(|e| e.to_str())
                                        .map(|e| e.eq_ignore_ascii_case("exe") || e.eq_ignore_ascii_case("bat"))
                                        .unwrap_or(false);

                                    let display_name = folder_name.replace(['_', '-'], " ");
                                    let default_opts = WineOpts::default();

                                    let _ = create_launcher_script(
                                        &current_folder,
                                        rel,
                                        &display_name,
                                        is_windows,
                                        None,
                                        Some(&default_opts),
                                    );

                                    let record = GameRecord {
                                        dir: folder_name.clone(),
                                        display_name: display_name.clone(),
                                        binary: rel.to_string_lossy().to_string(),
                                        is_windows,
                                        wine_prefix: None,
                                        wine_opts: Some(default_opts),
                                        icon: Some(if is_windows { "💻".to_string() } else { "🐧".to_string() }),
                                        launcher_script: Some("start_game.sh".to_string()),
                                        desktop_entry: None,
                                        ignored: false,
                                        custom_wrapper: false,
                                        favorite: false,
                                        rating: 0,
                                        playtime_seconds: 0,
                                        play_count: 0,
                                        last_played: None,
                                        hidden: false,
                                    };

                                    let _ = app.db.upsert_game(&record);
                                    app.set_toast(format!("✓ Added '{}' ({})", display_name, rel.display()));
                                }
                            }

                            if current_idx + 1 < folders.len() {
                                current_idx += 1;
                                let next_folder = &folders[current_idx];
                                binaries = scan_executables(next_folder, 2);
                                filtered_indices = (0..binaries.len()).collect();
                                selected_bin = 0;
                                search_query.clear();
                                is_searching = true;
                                ActiveModal::NewGameWizard {
                                    folders,
                                    current_idx,
                                    binaries,
                                    filtered_indices,
                                    selected_bin,
                                    search_query,
                                    is_searching,
                                }
                            } else {
                                app.reload_games();
                                ActiveModal::None
                            }
                        }
                        _ => ActiveModal::NewGameWizard {
                            folders,
                            current_idx,
                            binaries,
                            filtered_indices,
                            selected_bin,
                            search_query,
                            is_searching,
                        },
                    }
                }
            } else {
                // Selection Mode: j/k = navigate, g/G = top/bottom, s = skip, i = ignore, / = search mode
                if key.modifiers.contains(KeyModifiers::CONTROL) {
                    match key.code {
                        KeyCode::Char('d') => {
                            if !filtered_indices.is_empty() {
                                selected_bin = (selected_bin + 8).min(filtered_indices.len() - 1);
                            }
                        }
                        KeyCode::Char('u') => {
                            selected_bin = selected_bin.saturating_sub(8);
                        }
                        _ => {}
                    }
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        filtered_indices,
                        selected_bin,
                        search_query,
                        is_searching,
                    }
                } else {
                    match key.code {
                        KeyCode::Char('/') => {
                            is_searching = true;
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Char('s') => {
                            if current_idx + 1 < folders.len() {
                                current_idx += 1;
                                let next_folder = &folders[current_idx];
                                binaries = scan_executables(next_folder, 2);
                                filtered_indices = (0..binaries.len()).collect();
                                selected_bin = 0;
                                search_query.clear();
                                is_searching = true;
                                ActiveModal::NewGameWizard {
                                    folders,
                                    current_idx,
                                    binaries,
                                    filtered_indices,
                                    selected_bin,
                                    search_query,
                                    is_searching,
                                }
                            } else {
                                app.reload_games();
                                ActiveModal::None
                            }
                        }
                        KeyCode::Char('i') => {
                            let record = GameRecord {
                                dir: folder_name.clone(),
                                display_name: folder_name.replace(['_', '-'], " "),
                                binary: String::new(),
                                is_windows: false,
                                wine_prefix: None,
                                wine_opts: None,
                                icon: None,
                                launcher_script: None,
                                desktop_entry: None,
                                ignored: true,
                                custom_wrapper: false,
                                favorite: false,
                                rating: 0,
                                playtime_seconds: 0,
                                play_count: 0,
                                last_played: None,
                                hidden: false,
                            };
                            let _ = app.db.upsert_game(&record);
                            app.set_toast(format!("🚫 Ignored folder '{}'", folder_name));

                            if current_idx + 1 < folders.len() {
                                current_idx += 1;
                                let next_folder = &folders[current_idx];
                                binaries = scan_executables(next_folder, 2);
                                filtered_indices = (0..binaries.len()).collect();
                                selected_bin = 0;
                                search_query.clear();
                                is_searching = true;
                                ActiveModal::NewGameWizard {
                                    folders,
                                    current_idx,
                                    binaries,
                                    filtered_indices,
                                    selected_bin,
                                    search_query,
                                    is_searching,
                                }
                            } else {
                                app.reload_games();
                                ActiveModal::None
                            }
                        }
                        KeyCode::Char('k') | KeyCode::Up => {
                            if selected_bin > 0 {
                                selected_bin -= 1;
                            } else if !filtered_indices.is_empty() {
                                selected_bin = filtered_indices.len() - 1;
                            }
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Char('j') | KeyCode::Down => {
                            if !filtered_indices.is_empty() {
                                selected_bin = (selected_bin + 1) % filtered_indices.len();
                            }
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Char('g') | KeyCode::Home => {
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin: 0,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Char('G') | KeyCode::End => {
                            let last = filtered_indices.len().saturating_sub(1);
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin: last,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::PageUp => {
                            selected_bin = selected_bin.saturating_sub(8);
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::PageDown => {
                            if !filtered_indices.is_empty() {
                                selected_bin = (selected_bin + 8).min(filtered_indices.len() - 1);
                            }
                            ActiveModal::NewGameWizard {
                                folders,
                                current_idx,
                                binaries,
                                filtered_indices,
                                selected_bin,
                                search_query,
                                is_searching,
                            }
                        }
                        KeyCode::Esc | KeyCode::Char('q') => {
                            if current_idx + 1 < folders.len() {
                                current_idx += 1;
                                let next_folder = &folders[current_idx];
                                binaries = scan_executables(next_folder, 2);
                                filtered_indices = (0..binaries.len()).collect();
                                selected_bin = 0;
                                search_query.clear();
                                is_searching = true;
                                ActiveModal::NewGameWizard {
                                    folders,
                                    current_idx,
                                    binaries,
                                    filtered_indices,
                                    selected_bin,
                                    search_query,
                                    is_searching,
                                }
                            } else {
                                app.reload_games();
                                ActiveModal::None
                            }
                        }
                        _ => ActiveModal::NewGameWizard {
                            folders,
                            current_idx,
                            binaries,
                            filtered_indices,
                            selected_bin,
                            search_query,
                            is_searching,
                        },
                    }
                }
            }
        }
        ActiveModal::ResetScriptConfirmation { game_name } => match key.code {
            KeyCode::Esc | KeyCode::Char('n') | KeyCode::Char('q') => ActiveModal::None,
            KeyCode::Enter => {
                if let Some(game) = app.selected_game().cloned() {
                    let folder = app.games_root.join(&game.dir);
                    let script_path = folder.join("start_game.sh");
                    // Delete existing file to force fresh generation (bypasses marker patching)
                    let _ = fs::remove_file(&script_path);
                    let _ = create_launcher_script(
                        &folder,
                        Path::new(&game.binary),
                        &game.display_name,
                        game.is_windows,
                        game.wine_prefix.as_deref().map(Path::new),
                        game.wine_opts.as_ref(),
                    );
                    let mut updated = game.clone();
                    updated.custom_wrapper = false;
                    let _ = app.db.upsert_game(&updated);
                    app.set_toast(format!("🔄 Reset launcher script for '{}'", game.display_name));
                    app.reload_games();
                }
                ActiveModal::None
            }
            _ => ActiveModal::ResetScriptConfirmation { game_name },
        },
        ActiveModal::None => ActiveModal::None,
    };

    app.active_modal = next_modal;
}

fn apply_keyd_patch(app: &mut App, patch: Option<String>) {
    if let Some(game) = app.selected_game().cloned() {
        let folder = app.games_root.join(&game.dir);
        let mut opts = game.wine_opts.clone().unwrap_or_default();
        opts.keyd_remap = patch.clone();

        let mut updated = game.clone();
        updated.wine_opts = Some(opts.clone());
        let _ = app.db.upsert_game(&updated);

        let _ = create_launcher_script(
            &folder,
            Path::new(&game.binary),
            &game.display_name,
            game.is_windows,
            game.wine_prefix.as_deref().map(Path::new),
            Some(&opts),
        );

        let status = patch.as_deref().unwrap_or("Disabled");
        app.set_toast(format!("✓ Set keyd patch for '{}' to: {}", game.display_name, status));
        app.reload_games();
    }
}

fn which_bin(name: &str) -> bool {
    std::env::var_os("PATH")
        .and_then(|paths| {
            std::env::split_paths(&paths).find_map(|p| {
                let full = p.join(name);
                if full.is_file() {
                    Some(full)
                } else {
                    None
                }
            })
        })
        .is_some()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_app_with_game() -> (tempfile::TempDir, App) {
        make_app_with_game_impl(false)
    }

    fn make_app_with_windows_game() -> (tempfile::TempDir, App) {
        make_app_with_game_impl(true)
    }

    fn make_app_with_game_impl(is_windows: bool) -> (tempfile::TempDir, App) {
        let dir = tempfile::tempdir().unwrap();
        let mut app = App::new(dir.path().to_path_buf());

        // Exit search mode so hotkeys reach the main dashboard match
        app.is_searching = false;

        let game = GameRecord {
            dir: "test_game".into(),
            display_name: "Test Game".into(),
            binary: if is_windows { "game.exe" } else { "game" }.into(),
            is_windows,
            wine_prefix: None,
            wine_opts: None,
            icon: None,
            launcher_script: None,
            desktop_entry: None,
            ignored: false,
            custom_wrapper: false,
            favorite: false,
            rating: 5,
            playtime_seconds: 0,
            play_count: 0,
            last_played: None,
            hidden: false,
        };

        app.db.upsert_game(&game).unwrap();
        app.reload_games();
        (dir, app)
    }

    #[test]
    fn ctrl_r_opens_reset_confirmation_not_rate_game() {
        let (_dir, mut app) = make_app_with_game();

        let key = KeyEvent::new(KeyCode::Char('r'), KeyModifiers::CONTROL);
        handle_key_event(&mut app, key);

        match &app.active_modal {
            ActiveModal::ResetScriptConfirmation { game_name } => {
                assert_eq!(game_name, "Test Game");
            }
            other => panic!(
                "Ctrl+r should open ResetScriptConfirmation, got {:?}",
                std::mem::discriminant(other)
            ),
        }
    }

    #[test]
    fn plain_r_opens_rate_game() {
        let (_dir, mut app) = make_app_with_game();

        let key = KeyEvent::new(KeyCode::Char('r'), KeyModifiers::NONE);
        handle_key_event(&mut app, key);

        match &app.active_modal {
            ActiveModal::RateGame { .. } => {}
            other => panic!(
                "Plain 'r' should open RateGame, got {:?}",
                std::mem::discriminant(other)
            ),
        }
    }

    fn exec_modal_selected(app: &App) -> usize {
        match &app.active_modal {
            ActiveModal::ExecutionSettings { selected_opt, .. } => *selected_opt,
            other => panic!(
                "expected ExecutionSettings modal, got {:?}",
                std::mem::discriminant(other)
            ),
        }
    }

    fn exec_modal_opts(app: &App) -> WineOpts {
        match &app.active_modal {
            ActiveModal::ExecutionSettings { opts, .. } => opts.clone(),
            other => panic!(
                "expected ExecutionSettings modal, got {:?}",
                std::mem::discriminant(other)
            ),
        }
    }

    #[test]
    fn windows_exec_settings_cycles_three_rows_in_place() {
        let (_dir, mut app) = make_app_with_windows_game();

        // Open Execution Settings for the Windows game.
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char('c'), KeyModifiers::NONE));
        match &app.active_modal {
            ActiveModal::ExecutionSettings {
                is_windows,
                selected_opt,
                ..
            } => {
                assert!(*is_windows, "should open for the Windows game");
                assert_eq!(*selected_opt, 0);
            }
            other => panic!(
                "'c' should open ExecutionSettings, got {:?}",
                std::mem::discriminant(other)
            ),
        }

        // Hammer 'j' far beyond the old 7-row range: selection must never exceed 2.
        for _ in 0..20 {
            handle_key_event(&mut app, KeyEvent::new(KeyCode::Char('j'), KeyModifiers::NONE));
            let sel = exec_modal_selected(&app);
            assert!(sel <= 2, "selected_opt {} must never exceed 2", sel);
        }

        // 'g' -> row 0; 'k' from row 0 wraps to 2; 'G' -> row 2.
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char('g'), KeyModifiers::NONE));
        assert_eq!(exec_modal_selected(&app), 0);
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char('k'), KeyModifiers::NONE));
        assert_eq!(exec_modal_selected(&app), 2);
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char('G'), KeyModifiers::NONE));
        assert_eq!(exec_modal_selected(&app), 2);

        // Row 2 (SDL driver): Auto -> x11 -> Auto. Cycling keeps the modal open
        // and the applied value lands in the DB record, not just the modal state.
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        assert!(matches!(app.active_modal, ActiveModal::ExecutionSettings { .. }), "modal should stay open after cycling");
        assert_eq!(exec_modal_opts(&app).sdl_driver.as_deref(), Some("x11"));
        assert_eq!(
            app.selected_game()
                .and_then(|g| g.wine_opts.as_ref())
                .and_then(|o| o.sdl_driver.as_deref()),
            Some("x11"),
            "cycled SDL value must be persisted to the game record"
        );
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        assert_eq!(exec_modal_opts(&app).sdl_driver.as_deref(), None);

        // Row 1 (DXVK HUD): Off -> fps -> full -> Off.
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char('k'), KeyModifiers::NONE));
        assert_eq!(exec_modal_selected(&app), 1);
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        assert_eq!(exec_modal_opts(&app).dxvk_hud.as_deref(), Some("fps"));
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        assert_eq!(exec_modal_opts(&app).dxvk_hud.as_deref(), Some("full"));
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        assert_eq!(exec_modal_opts(&app).dxvk_hud.as_deref(), None);

        // Row 0 (Virtual Desktop Resolution): Native -> 1920x1080 -> 1280x720 -> Native.
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char('k'), KeyModifiers::NONE));
        assert_eq!(exec_modal_selected(&app), 0);
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        assert_eq!(exec_modal_opts(&app).resolution.as_deref(), Some("1920x1080"));
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        assert_eq!(exec_modal_opts(&app).resolution.as_deref(), Some("1280x720"));
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE));
        assert_eq!(exec_modal_opts(&app).resolution.as_deref(), None);

        // Esc closes the modal.
        handle_key_event(&mut app, KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE));
        assert!(matches!(app.active_modal, ActiveModal::None));
    }
}
