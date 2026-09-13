use rand::seq::SliceRandom;
use serde::Deserialize;
use std::io::{stdout, Write};
use std::time::Duration;
use unicode_width::UnicodeWidthStr;

use crate::config::user_name;

const COLOR_RESET: &str = "\x1b[0m";
const COLOR_BOLD: &str = "\x1b[1m";
const COLOR_YELLOW: &str = "\x1b[33m";
const COLOR_CYAN: &str = "\x1b[36m";
const COLOR_GREEN: &str = "\x1b[32m";
const COLOR_GREY: &str = "\x1b[90m";
const COLOR_MAGENTA: &str = "\x1b[35m";

#[derive(Deserialize)]
struct DummyJsonQuote {
    quote: Option<String>,
    author: Option<String>,
}

#[derive(Deserialize)]
struct StoicQuote {
    text: Option<String>,
    author: Option<String>,
}

pub fn fetch_online_quote() -> String {
    let urls = [
        "https://dummyjson.com/quotes/random",
        "https://api.stoicquote.com/quote",
    ];

    for url in urls {
        let resp = ureq::get(url)
            .timeout(Duration::from_millis(1500))
            .set("User-Agent", "GameLauncher/2.0")
            .call();

        if let Ok(response) = resp {
            if response.status() == 200 {
                let reader = response.into_reader();
                if url.contains("dummyjson") {
                    if let Ok(q) = serde_json::from_reader::<_, DummyJsonQuote>(reader) {
                        if let Some(text) = q.quote {
                            let author = q.author.unwrap_or_else(|| "Unknown".to_string());
                            return format!("\"{}\" — {}", text, author);
                        }
                    }
                } else if let Ok(q) = serde_json::from_reader::<_, StoicQuote>(reader) {
                    if let Some(text) = q.text {
                        let author = q.author.unwrap_or_else(|| "Unknown".to_string());
                        return format!("\"{}\" — {}", text, author);
                    }
                }
            }
        }
    }

    let user = user_name();
    let fallbacks = [
        format!("\"Praise the Sun! ☀️ Hope you enjoyed that run, {}!\"", user),
        format!("\"GG WP! Great session, {}!\"", user),
        "\"The cake may be a lie, but that run was 100% real!\"".to_string(),
        "\"Victory or defeat, every session makes you stronger!\"".to_string(),
        "\"Stay hydrated and see you in the dungeon next time! 🏰\"".to_string(),
    ];

    let mut rng = rand::thread_rng();
    fallbacks.choose(&mut rng).cloned().unwrap_or_else(|| {
        "\"Fiction is the truth inside the lie.\" — Stephen King".to_string()
    })
}

pub fn format_exact_session_duration(seconds: u64) -> String {
    if seconds < 60 {
        return format!("{}s", seconds);
    }
    let mins = seconds / 60;
    let secs = seconds % 60;
    if mins < 60 {
        if secs > 0 {
            format!("{}m {}s", mins, secs)
        } else {
            format!("{}m", mins)
        }
    } else {
        let hours = mins / 60;
        let rem_m = mins % 60;
        format!("{}h {}m", hours, rem_m)
    }
}

fn strip_ansi(s: &str) -> String {
    let mut out = String::new();
    let mut in_escape = false;
    for ch in s.chars() {
        if ch == '\x1b' {
            in_escape = true;
        } else if in_escape {
            if ch == 'm' {
                in_escape = false;
            }
        } else {
            out.push(ch);
        }
    }
    out
}

fn pad_to(s: &str, target_width: usize) -> String {
    let plain = strip_ansi(s);
    let visual_w = UnicodeWidthStr::width(plain.as_str());
    if visual_w >= target_width {
        s.to_string()
    } else {
        format!("{}{}", s, " ".repeat(target_width - visual_w))
    }
}

fn truncate_vw(s: &str, max_width: usize) -> String {
    let visual_w = UnicodeWidthStr::width(s);
    if visual_w <= max_width {
        return s.to_string();
    }
    let mut out = String::new();
    let budget = if max_width > 1 { max_width - 1 } else { max_width };
    for ch in s.chars() {
        let test = format!("{}{}", out, ch);
        if UnicodeWidthStr::width(test.as_str()) > budget {
            break;
        }
        out.push(ch);
    }
    format!("{}…", out)
}

fn wrap_text(text: &str, max_width: usize) -> Vec<String> {
    let mut lines = Vec::new();
    for paragraph in text.lines() {
        let mut cur_line = String::new();
        for word in paragraph.split_whitespace() {
            if cur_line.is_empty() {
                cur_line.push_str(word);
            } else {
                let test = format!("{} {}", cur_line, word);
                if UnicodeWidthStr::width(test.as_str()) <= max_width {
                    cur_line = test;
                } else {
                    lines.push(cur_line);
                    cur_line = word.to_string();
                }
            }
        }
        if !cur_line.is_empty() {
            lines.push(cur_line);
        }
    }
    if lines.is_empty() {
        lines.push(text.to_string());
    }
    lines
}

pub fn render_post_game_recap(
    game_name: &str,
    session_sec: u64,
    total_sec: u64,
    play_count: u64,
    rating: u8,
    is_windows: bool,
) {
    // Clear terminal screen
    print!("\x1b[H\x1b[2J");
    let _ = stdout().flush();

    let sess_str = format_exact_session_duration(session_sec);
    let tot_str = crate::model::format_playtime(total_sec);
    let quote = fetch_online_quote();

    let stars_formatted = match rating {
        1..=5 => {
            let label = match rating {
                5 => "Masterpiece",
                4 => "Great",
                3 => "Good",
                2 => "Mediocre",
                _ => "Bad",
            };
            format!("{}  {}({}/5 • {}){}", "⭐".repeat(rating as usize), COLOR_GREY, rating, label, COLOR_RESET)
        }
        _ => format!("{}Unrated{}", COLOR_GREY, COLOR_RESET),
    };

    let platform_str = if is_windows {
        format!("{}Windows (Wine/Proton){}", COLOR_CYAN, COLOR_RESET)
    } else {
        format!("{}Linux Native{}", COLOR_GREEN, COLOR_RESET)
    };

    let now_str = chrono::Local::now().format("%a, %b %d • %H:%M").to_string();

    let (term_cols, term_rows) = match crossterm::terminal::size() {
        Ok((cols, rows)) => (cols as usize, rows as usize),
        Err(_) => (80, 24),
    };

    let card_width = term_cols.saturating_sub(10).clamp(54, 88);
    let inner_width = card_width - 2;
    let left_pad = (term_cols.saturating_sub(card_width)) / 2;
    let p_str = " ".repeat(left_pad);

    let dash_len = inner_width;
    let dashes = "─".repeat(dash_len);
    let top_line = format!("{}{}✨ ╭{}╮ ✨{}", p_str, COLOR_CYAN, dashes, COLOR_RESET);
    let divider = format!("{}{}   ├{}┤   {}", p_str, COLOR_CYAN, dashes, COLOR_RESET);
    let bottom_line = format!("{}{}✨ ╰{}╯ ✨{}", p_str, COLOR_CYAN, dashes, COLOR_RESET);

    let hdr_prefix = format!("  🎮 {}{}GAME SESSION RECAP:{} {}", COLOR_BOLD, COLOR_YELLOW, COLOR_RESET, COLOR_BOLD);
    let hdr_plain = "  🎮 GAME SESSION RECAP: ";
    let max_title_w = inner_width.saturating_sub(UnicodeWidthStr::width(hdr_plain) + 2);
    let truncated_title = truncate_vw(game_name, max_title_w);
    let header_content = format!("{}{}{}", hdr_prefix, truncated_title, COLOR_RESET);
    let row1 = format!("{p_str}{COLOR_CYAN}   │{COLOR_RESET}{}{COLOR_CYAN}│   {COLOR_RESET}", pad_to(&header_content, inner_width));

    let label_w = 26;
    let lbl1 = "  🕒  Session Duration";
    let lbl2 = "  ⌛  Total Playtime";
    let lbl3 = "  ⭐  Rating";
    let lbl4 = "  📅  Session Ended";
    let lbl5 = "  💻  Platform";

    let val1 = format!("{}{}{}", COLOR_GREEN, sess_str, COLOR_RESET);
    let row_dur_content = format!("{}{}", pad_to(lbl1, label_w), val1);
    let row_dur = format!("{p_str}{COLOR_CYAN}   │{COLOR_RESET}{}{COLOR_CYAN}│   {COLOR_RESET}", pad_to(&row_dur_content, inner_width));

    let val2 = format!("{}{}{}   {}(Session #{}){}", COLOR_CYAN, tot_str, COLOR_RESET, COLOR_GREY, play_count, COLOR_RESET);
    let row_tot_content = format!("{}{}", pad_to(lbl2, label_w), val2);
    let row_tot = format!("{p_str}{COLOR_CYAN}   │{COLOR_RESET}{}{COLOR_CYAN}│   {COLOR_RESET}", pad_to(&row_tot_content, inner_width));

    let row_rat_content = format!("{}{}", pad_to(lbl3, label_w), stars_formatted);
    let row_rat = format!("{p_str}{COLOR_CYAN}   │{COLOR_RESET}{}{COLOR_CYAN}│   {COLOR_RESET}", pad_to(&row_rat_content, inner_width));

    let val4 = format!("{}{}{}", COLOR_GREY, now_str, COLOR_RESET);
    let row_date_content = format!("{}{}", pad_to(lbl4, label_w), val4);
    let row_date = format!("{p_str}{COLOR_CYAN}   │{COLOR_RESET}{}{COLOR_CYAN}│   {COLOR_RESET}", pad_to(&row_date_content, inner_width));

    let row_plat_content = format!("{}{}", pad_to(lbl5, label_w), platform_str);
    let row_plat = format!("{p_str}{COLOR_CYAN}   │{COLOR_RESET}{}{COLOR_CYAN}│   {COLOR_RESET}", pad_to(&row_plat_content, inner_width));

    let quote_prefix = "  💬  ";
    let quote_indent = "      ";
    let quote_max_w = inner_width.saturating_sub(UnicodeWidthStr::width(quote_prefix) + 2);

    let wrapped_quote = wrap_text(&quote, quote_max_w);
    let mut quote_rows = Vec::new();
    for (idx, ql) in wrapped_quote.iter().enumerate() {
        let content = if idx == 0 {
            format!("{}{}{}{}", quote_prefix, COLOR_MAGENTA, ql, COLOR_RESET)
        } else {
            format!("{}{}{}{}", quote_indent, COLOR_MAGENTA, ql, COLOR_RESET)
        };
        quote_rows.push(format!("{p_str}{COLOR_CYAN}   │{COLOR_RESET}{}{COLOR_CYAN}│   {COLOR_RESET}", pad_to(&content, inner_width)));
    }

    let mut box_lines = vec![
        top_line,
        row1,
        divider.clone(),
        row_dur,
        row_tot,
        row_rat,
        row_date,
        row_plat,
        divider,
    ];
    box_lines.extend(quote_rows);
    box_lines.push(bottom_line);

    let box_height = box_lines.len();
    let top_pad = (term_rows.saturating_sub(box_height)) / 2;

    for _ in 0..top_pad {
        println!();
    }
    for line in box_lines {
        println!("{}", line);
    }
    let _ = stdout().flush();
}
