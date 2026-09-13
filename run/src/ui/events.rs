use crossterm::event::{KeyCode, KeyEvent};
use fuzzy_matcher::skim::SkimMatcherV2;
use fuzzy_matcher::FuzzyMatcher;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::model::GameEntry;
use crate::scanner::{create_desktop_entry, create_launcher_script, scan_executables};
use crate::ui::app::{ActiveModal, App, WizardStep};

pub fn handle_key_event(app: &mut App, key: KeyEvent) {
    // 1. Handle Active Modals
    if !matches!(app.active_modal, ActiveModal::None) {
        handle_modal_key(app, key);
        return;
    }

    // 2. Handle Search Bar Input Mode
    if app.is_searching {
        match key.code {
            KeyCode::Esc | KeyCode::Enter => {
                app.is_searching = false;
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
    match key.code {
        KeyCode::Char('q') | KeyCode::Esc => {
            app.should_quit = true;
        }
        KeyCode::Char('/') => {
            app.is_searching = true;
        }
        KeyCode::Up => {
            app.select_prev();
        }
        KeyCode::Down => {
            app.select_next();
        }
        KeyCode::Enter => {
            if let Some(game) = app.selected_game().cloned() {
                app.launch_target = Some(game);
            }
        }
        KeyCode::Char('r') => {
            if let Some(game) = app.selected_game() {
                let current_rating = app.stats.get_stat(&game.dir).map(|s| s.rating).unwrap_or(0);

                let opt_idx = if current_rating == 0 {
                    5
                } else {
                    5 - (current_rating as usize)
                };

                app.active_modal = ActiveModal::RateGame {
                    selected_opt: opt_idx,
                };
            }
        }
        KeyCode::Char('k') => {
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

                let script_path = create_launcher_script(
                    &folder_path,
                    &binary_path,
                    &game.display_name,
                    game.is_windows,
                    wine_prefix.as_deref(),
                    game.wine_opts.as_ref(),
                );

                if let Ok(script) = script_path {
                    if let Some(entry) = app.registry.games.get_mut(&game.dir) {
                        entry.custom_wrapper = Some(true);
                        let _ = app.registry.save(&app.games_root);
                    }

                    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "nvim".to_string());
                    let _ = crossterm::terminal::disable_raw_mode();
                    let _ = crossterm::execute!(std::io::stdout(), crossterm::terminal::LeaveAlternateScreen);
                    let _ = Command::new(&editor).arg(&script).status();
                    let _ = crossterm::execute!(std::io::stdout(), crossterm::terminal::EnterAlternateScreen);
                    let _ = crossterm::terminal::enable_raw_mode();

                    app.set_toast(format!("Saved custom wrapper for '{}'", game.display_name));
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
                            if let Some(entry) = app.registry.games.get_mut(&game.dir) {
                                entry.desktop_entry = Some(p.to_string_lossy().to_string());
                                let _ = app.registry.save(&app.games_root);
                            }
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
                app.registry.games.remove(&game.dir);
                let _ = app.registry.save(&app.games_root);
                app.reload_games();
                app.set_toast(format!("🗑️ Removed '{}' (Stats preserved)", game.display_name));
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
            KeyCode::Esc => ActiveModal::None,
            KeyCode::Up => {
                if selected_opt > 0 {
                    selected_opt -= 1;
                } else {
                    selected_opt = 5;
                }
                ActiveModal::RateGame { selected_opt }
            }
            KeyCode::Down => {
                selected_opt = (selected_opt + 1) % 6;
                ActiveModal::RateGame { selected_opt }
            }
            KeyCode::Enter => {
                let chosen_rating = match selected_opt {
                    0 => 5,
                    1 => 4,
                    2 => 3,
                    3 => 2,
                    4 => 1,
                    _ => 0,
                };
                if let Some(game) = app.selected_game() {
                    let dir_key = game.dir.clone();
                    let g_name = game.display_name.clone();
                    let entry = app.stats.get_stat_mut(&dir_key);
                    entry.rating = chosen_rating;
                    let _ = app.stats.save(&app.games_root);
                    let stars = if chosen_rating > 0 {
                        "⭐".repeat(chosen_rating as usize)
                    } else {
                        "Unrated".to_string()
                    };
                    app.set_toast(format!("✓ Rated '{}' {}", g_name, stars));
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
                        apply_keyd_patch(app, Some(custom_input));
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
                    KeyCode::Esc => ActiveModal::None,
                    KeyCode::Up => {
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
                    KeyCode::Down => {
                        selected_opt = (selected_opt + 1) % 3;
                        ActiveModal::KeyboardPatch {
                            selected_opt,
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
        } => match key.code {
            KeyCode::Esc => ActiveModal::None,
            KeyCode::Up => {
                let max = 2;
                if selected_opt > 0 {
                    selected_opt -= 1;
                } else {
                    selected_opt = max;
                }
                ActiveModal::ExecutionSettings {
                    selected_opt,
                    is_windows,
                    opts,
                }
            }
            KeyCode::Down => {
                let max = 3;
                selected_opt = (selected_opt + 1) % max;
                ActiveModal::ExecutionSettings {
                    selected_opt,
                    is_windows,
                    opts,
                }
            }
            KeyCode::Char(' ') => {
                if is_windows {
                    match selected_opt {
                        0 => {
                            let next = match opts.resolution.as_deref() {
                                None => Some("1920x1080".to_string()),
                                Some("1920x1080") => Some("2560x1440".to_string()),
                                Some("2560x1440") => Some("1280x720".to_string()),
                                _ => None,
                            };
                            opts.resolution = next;
                        }
                        1 => {
                            let next = match opts.dxvk_hud.as_deref() {
                                None | Some("off") => Some("fps".to_string()),
                                Some("fps") => Some("full".to_string()),
                                _ => None,
                            };
                            opts.dxvk_hud = next;
                        }
                        2 => {
                            let next = match opts.sdl_driver.as_deref() {
                                None => Some("x11".to_string()),
                                Some("x11") => Some("wayland".to_string()),
                                _ => None,
                            };
                            opts.sdl_driver = next;
                        }
                        _ => {}
                    }
                } else {
                    match selected_opt {
                        0 => opts.sdl_driver = None,
                        1 => opts.sdl_driver = Some("x11".to_string()),
                        2 => opts.sdl_driver = Some("wayland".to_string()),
                        _ => {}
                    }
                }
                ActiveModal::ExecutionSettings {
                    selected_opt,
                    is_windows,
                    opts,
                }
            }
            KeyCode::Enter => {
                if let Some(game) = app.selected_game().cloned() {
                    if let Some(entry) = app.registry.games.get_mut(&game.dir) {
                        entry.wine_opts = Some(opts.clone());
                        let _ = app.registry.save(&app.games_root);

                        let folder = app.games_root.join(&game.dir);
                        let _ = create_launcher_script(
                            &folder,
                            Path::new(&game.binary),
                            &game.display_name,
                            game.is_windows,
                            game.wine_prefix.as_deref().map(Path::new),
                            Some(&opts),
                        );
                        app.set_toast(format!("✓ Updated execution settings for '{}'", game.display_name));
                    }
                }
                app.reload_games();
                ActiveModal::None
            }
            _ => ActiveModal::ExecutionSettings {
                selected_opt,
                is_windows,
                opts,
            },
        },
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

                                if let Some(entry) = app.registry.games.get_mut(&game.dir) {
                                    entry.binary = rel.to_string_lossy().to_string();
                                    entry.is_windows = is_windows;
                                    entry.icon = Some(if is_windows { "💻".to_string() } else { "🐧".to_string() });

                                    let _ = create_launcher_script(
                                        &folder,
                                        rel,
                                        &game.display_name,
                                        is_windows,
                                        game.wine_prefix.as_deref().map(Path::new),
                                        game.wine_opts.as_ref(),
                                    );
                                    let _ = app.registry.save(&app.games_root);
                                    app.set_toast(format!("✓ Main binary set to '{}'", rel.display()));
                                }
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
                        if let Some(entry) = app.registry.games.get_mut(&game.dir) {
                            entry.display_name = trimmed.to_string();
                            let folder = app.games_root.join(&game.dir);
                            let _ = create_launcher_script(
                                &folder,
                                Path::new(&entry.binary),
                                trimmed,
                                entry.is_windows,
                                entry.wine_prefix.as_deref().map(Path::new),
                                entry.wine_opts.as_ref(),
                            );
                            let _ = app.registry.save(&app.games_root);
                            app.set_toast(format!("✓ Renamed game to '{}'", trimmed));
                        }
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
            mut selected_bin,
            mut display_name,
            mut step,
            opts,
        } => match step {
            WizardStep::SelectBinary => match key.code {
                KeyCode::Esc | KeyCode::Char('s') => {
                    if current_idx + 1 < folders.len() {
                        current_idx += 1;
                        let next_folder = &folders[current_idx];
                        binaries = scan_executables(next_folder, 2);
                        selected_bin = 0;
                        display_name = next_folder
                            .file_name()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .replace(['_', '-'], " ");
                        step = WizardStep::SelectBinary;
                        ActiveModal::NewGameWizard {
                            folders,
                            current_idx,
                            binaries,
                            selected_bin,
                            display_name,
                            step,
                            opts,
                        }
                    } else {
                        ActiveModal::None
                    }
                }
                KeyCode::Up => {
                    if selected_bin > 0 {
                        selected_bin -= 1;
                    } else if !binaries.is_empty() {
                        selected_bin = binaries.len() - 1;
                    }
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        selected_bin,
                        display_name,
                        step,
                        opts,
                    }
                }
                KeyCode::Down => {
                    if !binaries.is_empty() {
                        selected_bin = (selected_bin + 1) % binaries.len();
                    }
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        selected_bin,
                        display_name,
                        step,
                        opts,
                    }
                }
                KeyCode::Enter => {
                    if !binaries.is_empty() {
                        step = WizardStep::NameGame;
                    }
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        selected_bin,
                        display_name,
                        step,
                        opts,
                    }
                }
                _ => ActiveModal::NewGameWizard {
                    folders,
                    current_idx,
                    binaries,
                    selected_bin,
                    display_name,
                    step,
                    opts,
                },
            },
            WizardStep::NameGame => match key.code {
                KeyCode::Backspace => {
                    display_name.pop();
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        selected_bin,
                        display_name,
                        step,
                        opts,
                    }
                }
                KeyCode::Char(c) => {
                    display_name.push(c);
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        selected_bin,
                        display_name,
                        step,
                        opts,
                    }
                }
                KeyCode::Enter => {
                    if !display_name.trim().is_empty() {
                        step = WizardStep::ConfigureSettings;
                    }
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        selected_bin,
                        display_name,
                        step,
                        opts,
                    }
                }
                _ => ActiveModal::NewGameWizard {
                    folders,
                    current_idx,
                    binaries,
                    selected_bin,
                    display_name,
                    step,
                    opts,
                },
            },
            WizardStep::ConfigureSettings => {
                if key.code == KeyCode::Enter {
                    let folder = &folders[current_idx];
                    let dir_name = folder.file_name().unwrap_or_default().to_string_lossy().to_string();
                    if let Some(bin) = binaries.get(selected_bin) {
                        let rel = bin.strip_prefix(folder).unwrap_or(bin);
                        let is_windows = rel
                            .extension()
                            .and_then(|e| e.to_str())
                            .map(|e| e.eq_ignore_ascii_case("exe") || e.eq_ignore_ascii_case("bat"))
                            .unwrap_or(false);

                        let _ = create_launcher_script(
                            folder,
                            rel,
                            &display_name,
                            is_windows,
                            None,
                            Some(&opts),
                        );

                        app.registry.games.insert(
                            dir_name.clone(),
                            GameEntry {
                                dir: dir_name.clone(),
                                display_name: display_name.clone(),
                                binary: rel.to_string_lossy().to_string(),
                                is_windows,
                                wine_prefix: None,
                                wine_opts: Some(opts.clone()),
                                icon: Some(if is_windows { "💻".to_string() } else { "🐧".to_string() }),
                                launcher_script: Some("start_game.sh".to_string()),
                                desktop_entry: None,
                                ignored: Some(false),
                                custom_wrapper: Some(false),
                            },
                        );

                        let _ = app.registry.save(&app.games_root);
                        app.set_toast(format!("✓ Registered '{}'", display_name));
                    }

                    if current_idx + 1 < folders.len() {
                        current_idx += 1;
                        let next_folder = &folders[current_idx];
                        binaries = scan_executables(next_folder, 2);
                        selected_bin = 0;
                        display_name = next_folder
                            .file_name()
                            .unwrap_or_default()
                            .to_string_lossy()
                            .replace(['_', '-'], " ");
                        step = WizardStep::SelectBinary;
                        ActiveModal::NewGameWizard {
                            folders,
                            current_idx,
                            binaries,
                            selected_bin,
                            display_name,
                            step,
                            opts,
                        }
                    } else {
                        app.reload_games();
                        ActiveModal::None
                    }
                } else {
                    ActiveModal::NewGameWizard {
                        folders,
                        current_idx,
                        binaries,
                        selected_bin,
                        display_name,
                        step,
                        opts,
                    }
                }
            }
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

        if let Some(entry) = app.registry.games.get_mut(&game.dir) {
            entry.wine_opts = Some(opts.clone());
            let _ = app.registry.save(&app.games_root);

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
        }
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
