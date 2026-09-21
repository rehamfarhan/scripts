use rusqlite::{params, Connection, Result};
use std::fs;
use std::path::Path;

use crate::model::{GameEntry, GameRegistry, GameStats, WineOpts};

#[derive(Debug, Clone)]
pub struct GameRecord {
    pub dir: String,
    pub display_name: String,
    pub binary: String,
    pub is_windows: bool,
    pub wine_prefix: Option<String>,
    pub wine_opts: Option<WineOpts>,
    pub icon: Option<String>,
    pub launcher_script: Option<String>,
    pub desktop_entry: Option<String>,
    pub ignored: bool,
    pub custom_wrapper: bool,
    pub favorite: bool,
    pub rating: u8, // 0 - 10 rating scale
    pub playtime_seconds: u64,
    pub play_count: u64,
    pub last_played: Option<String>,
    pub hidden: bool,
}

impl GameRecord {
    #[allow(dead_code)]
    pub fn to_game_entry(&self) -> GameEntry {
        GameEntry {
            dir: self.dir.clone(),
            display_name: self.display_name.clone(),
            binary: self.binary.clone(),
            is_windows: self.is_windows,
            wine_prefix: self.wine_prefix.clone(),
            wine_opts: self.wine_opts.clone(),
            icon: self.icon.clone(),
            launcher_script: self.launcher_script.clone(),
            desktop_entry: self.desktop_entry.clone(),
            ignored: Some(self.ignored),
            custom_wrapper: Some(self.custom_wrapper),
        }
    }

    #[allow(dead_code)]
    pub fn is_hidden(&self) -> bool {
        self.hidden
    }
}

pub struct Database {
    conn: Connection,
}

impl Database {
    pub fn open(games_root: &Path) -> Result<Self> {
        let db_path = games_root.join(".run.db");
        let conn = Connection::open(&db_path)?;

        conn.execute_batch(
            "
            CREATE TABLE IF NOT EXISTS games (
                dir TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                binary TEXT NOT NULL,
                is_windows INTEGER NOT NULL DEFAULT 0,
                wine_prefix TEXT,
                wine_opts TEXT,
                icon TEXT,
                launcher_script TEXT,
                desktop_entry TEXT,
                ignored INTEGER NOT NULL DEFAULT 0,
                custom_wrapper INTEGER NOT NULL DEFAULT 0,
                favorite INTEGER NOT NULL DEFAULT 0,
                rating INTEGER NOT NULL DEFAULT 0,
                playtime_seconds INTEGER NOT NULL DEFAULT 0,
                play_count INTEGER NOT NULL DEFAULT 0,
                last_played TEXT,
                hidden INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_dir TEXT NOT NULL,
                start_time TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL
            );
            ",
        )?;

        // Migration: add hidden column to existing databases that lack it
        let has_hidden: bool = conn
            .prepare("SELECT hidden FROM games LIMIT 1")
            .is_ok();
        if !has_hidden {
            conn.execute_batch("ALTER TABLE games ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;")?;
        }

        let db = Self { conn };
        db.auto_migrate_from_json(games_root);
        Ok(db)
    }

    fn auto_migrate_from_json(&self, games_root: &Path) {
        let reg_path = games_root.join(".run_registry.json");
        let stats_path = games_root.join(".run_stats.json");

        if !reg_path.is_file() && !stats_path.is_file() {
            return;
        }

        let registry = GameRegistry::load(games_root);
        let stats = GameStats::load(games_root);

        for (dir_name, entry) in registry.games {
            let stat = stats.get_stat(&dir_name);
            // Convert legacy 5-star rating (1..5) to 10-star rating (2..10)
            let legacy_rating = stat.map(|s| s.rating).unwrap_or(0);
            let rating_10 = if legacy_rating > 0 { legacy_rating.min(5) * 2 } else { 0 };

            let playtime = stat.map(|s| s.playtime_seconds).unwrap_or(0);
            let play_count = stat.map(|s| s.play_count).unwrap_or(0);
            let last_played = stat.and_then(|s| s.last_played.clone());

            let record = GameRecord {
                dir: dir_name,
                display_name: entry.display_name,
                binary: entry.binary,
                is_windows: entry.is_windows,
                wine_prefix: entry.wine_prefix,
                wine_opts: entry.wine_opts,
                icon: entry.icon,
                launcher_script: entry.launcher_script,
                desktop_entry: entry.desktop_entry,
                ignored: entry.ignored.unwrap_or(false),
                custom_wrapper: entry.custom_wrapper.unwrap_or(false),
                favorite: false,
                rating: rating_10,
                playtime_seconds: playtime,
                play_count,
                last_played,
                hidden: false,
            };

            let _ = self.upsert_game(&record);
        }

        // Backup old JSON files to prevent repeat migration
        if reg_path.is_file() {
            let _ = fs::rename(&reg_path, games_root.join(".run_registry.json.bak"));
        }
        if stats_path.is_file() {
            let _ = fs::rename(&stats_path, games_root.join(".run_stats.json.bak"));
        }
    }

    pub fn get_all_games(&self) -> Result<Vec<GameRecord>> {
        let mut stmt = self.conn.prepare(
            "SELECT dir, display_name, binary, is_windows, wine_prefix, wine_opts, icon,
                    launcher_script, desktop_entry, ignored, custom_wrapper, favorite,
                    rating, playtime_seconds, play_count, last_played, hidden
             FROM games
             WHERE hidden = 0",
        )?;

        let rows = stmt.query_map([], |row| {
            let wine_opts_json: Option<String> = row.get(5)?;
            let wine_opts: Option<WineOpts> = wine_opts_json
                .as_deref()
                .and_then(|s| serde_json::from_str(s).ok());

            Ok(GameRecord {
                dir: row.get(0)?,
                display_name: row.get(1)?,
                binary: row.get(2)?,
                is_windows: row.get::<_, i32>(3)? != 0,
                wine_prefix: row.get(4)?,
                wine_opts,
                icon: row.get(6)?,
                launcher_script: row.get(7)?,
                desktop_entry: row.get(8)?,
                ignored: row.get::<_, i32>(9)? != 0,
                custom_wrapper: row.get::<_, i32>(10)? != 0,
                favorite: row.get::<_, i32>(11)? != 0,
                rating: row.get(12)?,
                playtime_seconds: row.get::<_, i64>(13)? as u64,
                play_count: row.get::<_, i64>(14)? as u64,
                last_played: row.get(15)?,
                hidden: row.get::<_, i32>(16)? != 0,
            })
        })?;

        let mut games = Vec::new();
        for r in rows.flatten() {
            games.push(r);
        }
        Ok(games)
    }

    pub fn get_game(&self, dir_key: &str) -> Option<GameRecord> {
        let mut stmt = self.conn.prepare(
            "SELECT dir, display_name, binary, is_windows, wine_prefix, wine_opts, icon,
                    launcher_script, desktop_entry, ignored, custom_wrapper, favorite,
                    rating, playtime_seconds, play_count, last_played, hidden
             FROM games WHERE (dir = ?1 OR LOWER(dir) = LOWER(?1)) AND hidden = 0",
        ).ok()?;

        let mut rows = stmt.query_map(params![dir_key], |row| {
            let wine_opts_json: Option<String> = row.get(5)?;
            let wine_opts: Option<WineOpts> = wine_opts_json
                .as_deref()
                .and_then(|s| serde_json::from_str(s).ok());

            Ok(GameRecord {
                dir: row.get(0)?,
                display_name: row.get(1)?,
                binary: row.get(2)?,
                is_windows: row.get::<_, i32>(3)? != 0,
                wine_prefix: row.get(4)?,
                wine_opts,
                icon: row.get(6)?,
                launcher_script: row.get(7)?,
                desktop_entry: row.get(8)?,
                ignored: row.get::<_, i32>(9)? != 0,
                custom_wrapper: row.get::<_, i32>(10)? != 0,
                favorite: row.get::<_, i32>(11)? != 0,
                rating: row.get(12)?,
                playtime_seconds: row.get::<_, i64>(13)? as u64,
                play_count: row.get::<_, i64>(14)? as u64,
                last_played: row.get(15)?,
                hidden: row.get::<_, i32>(16)? != 0,
            })
        }).ok()?;

        rows.next()?.ok()
    }

    pub fn upsert_game(&self, game: &GameRecord) -> Result<()> {
        let wine_opts_json = game
            .wine_opts
            .as_ref()
            .and_then(|o| serde_json::to_string(o).ok());

        self.conn.execute(
            "INSERT INTO games (
                dir, display_name, binary, is_windows, wine_prefix, wine_opts, icon,
                launcher_script, desktop_entry, ignored, custom_wrapper, favorite,
                rating, playtime_seconds, play_count, last_played, hidden
            ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17)
            ON CONFLICT(dir) DO UPDATE SET
                display_name = excluded.display_name,
                binary = excluded.binary,
                is_windows = excluded.is_windows,
                wine_prefix = excluded.wine_prefix,
                wine_opts = excluded.wine_opts,
                icon = excluded.icon,
                launcher_script = excluded.launcher_script,
                desktop_entry = excluded.desktop_entry,
                ignored = excluded.ignored,
                custom_wrapper = excluded.custom_wrapper,
                favorite = excluded.favorite,
                rating = excluded.rating,
                playtime_seconds = excluded.playtime_seconds,
                play_count = excluded.play_count,
                last_played = excluded.last_played,
                hidden = 0",
            params![
                game.dir,
                game.display_name,
                game.binary,
                game.is_windows as i32,
                game.wine_prefix,
                wine_opts_json,
                game.icon,
                game.launcher_script,
                game.desktop_entry,
                game.ignored as i32,
                game.custom_wrapper as i32,
                game.favorite as i32,
                game.rating as i32,
                game.playtime_seconds as i64,
                game.play_count as i64,
                game.last_played,
                game.hidden as i32,
            ],
        )?;

        Ok(())
    }

    pub fn set_rating(&self, dir: &str, rating: u8) -> Result<()> {
        self.conn.execute(
            "UPDATE games SET rating = ?1 WHERE dir = ?2 OR LOWER(dir) = LOWER(?2)",
            params![rating as i32, dir],
        )?;
        Ok(())
    }

    pub fn toggle_favorite(&self, dir: &str) -> Result<bool> {
        let current = self
            .get_game(dir)
            .map(|g| g.favorite)
            .unwrap_or(false);
        let new_val = !current;
        self.conn.execute(
            "UPDATE games SET favorite = ?1 WHERE dir = ?2 OR LOWER(dir) = LOWER(?2)",
            params![new_val as i32, dir],
        )?;
        Ok(new_val)
    }

    pub fn record_session(
        &self,
        dir: &str,
        duration_seconds: u64,
        start_time: &str,
    ) -> Result<(u64, u64, u8)> {
        let tx = self.conn.unchecked_transaction()?;

        tx.execute(
            "INSERT INTO sessions (game_dir, start_time, duration_seconds) VALUES (?1, ?2, ?3)",
            params![dir, start_time, duration_seconds as i64],
        )?;

        tx.execute(
            "UPDATE games SET
                playtime_seconds = playtime_seconds + ?1,
                play_count = play_count + 1,
                last_played = ?2
             WHERE dir = ?3 OR LOWER(dir) = LOWER(?3)",
            params![duration_seconds as i64, start_time, dir],
        )?;

        tx.commit()?;

        if let Some(g) = self.get_game(dir) {
            Ok((g.playtime_seconds, g.play_count, g.rating))
        } else {
            Ok((duration_seconds, 1, 0))
        }
    }

    pub fn remove_game(&self, dir: &str) -> Result<()> {
        self.conn.execute(
            "UPDATE games SET hidden = 1 WHERE dir = ?1 OR LOWER(dir) = LOWER(?1)",
            params![dir],
        )?;
        Ok(())
    }

    /// Returns all dir keys (including hidden) so the onboarding wizard
    /// doesn't re-trigger for folders that were deliberately hidden.
    pub fn get_all_dir_keys(&self) -> Result<Vec<String>> {
        let mut stmt = self.conn.prepare("SELECT dir FROM games")?;
        let dirs: Vec<String> = stmt
            .query_map([], |row| row.get(0))?
            .filter_map(|r| r.ok())
            .collect();
        Ok(dirs)
    }

    /// Returns a game record regardless of hidden status — used by tests
    /// to verify stats survive soft delete.
    #[cfg(test)]
    pub fn get_game_any(&self, dir_key: &str) -> Option<GameRecord> {
        let mut stmt = self.conn.prepare(
            "SELECT dir, display_name, binary, is_windows, wine_prefix, wine_opts, icon,
                    launcher_script, desktop_entry, ignored, custom_wrapper, favorite,
                    rating, playtime_seconds, play_count, last_played, hidden
             FROM games WHERE dir = ?1 OR LOWER(dir) = LOWER(?1)",
        ).ok()?;

        let mut rows = stmt.query_map(params![dir_key], |row| {
            let wine_opts_json: Option<String> = row.get(5)?;
            let wine_opts: Option<WineOpts> = wine_opts_json
                .as_deref()
                .and_then(|s| serde_json::from_str(s).ok());

            Ok(GameRecord {
                dir: row.get(0)?,
                display_name: row.get(1)?,
                binary: row.get(2)?,
                is_windows: row.get::<_, i32>(3)? != 0,
                wine_prefix: row.get(4)?,
                wine_opts,
                icon: row.get(6)?,
                launcher_script: row.get(7)?,
                desktop_entry: row.get(8)?,
                ignored: row.get::<_, i32>(9)? != 0,
                custom_wrapper: row.get::<_, i32>(10)? != 0,
                favorite: row.get::<_, i32>(11)? != 0,
                rating: row.get(12)?,
                playtime_seconds: row.get::<_, i64>(13)? as u64,
                play_count: row.get::<_, i64>(14)? as u64,
                last_played: row.get(15)?,
                hidden: row.get::<_, i32>(16)? != 0,
            })
        }).ok()?;

        rows.next()?.ok()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};

    static TEST_DB_COUNTER: AtomicU64 = AtomicU64::new(0);

    fn temp_db() -> (Database, PathBuf) {
        let id = TEST_DB_COUNTER.fetch_add(1, Ordering::SeqCst);
        let dir = PathBuf::from(format!(
            "/tmp/run_test_{}_{:04}",
            std::process::id(),
            id
        ));
        let _ = fs::create_dir_all(&dir);
        let db = Database::open(&dir).expect("Failed to open test DB");
        (db, dir)
    }

    fn make_test_game(dir: &str) -> GameRecord {
        GameRecord {
            dir: dir.to_string(),
            display_name: format!("Game {}", dir),
            binary: "game.exe".to_string(),
            is_windows: true,
            wine_prefix: None,
            wine_opts: None,
            icon: Some("💻".to_string()),
            launcher_script: Some("start_game.sh".to_string()),
            desktop_entry: None,
            ignored: false,
            custom_wrapper: false,
            favorite: false,
            rating: 8,
            playtime_seconds: 3600,
            play_count: 5,
            last_played: Some("2026-01-15T10:00:00Z".to_string()),
            hidden: false,
        }
    }

    #[test]
    fn test_soft_delete_preserves_stats() {
        let (db, _dir) = temp_db();
        let game = make_test_game("my_game");
        db.upsert_game(&game).unwrap();

        // Verify game is visible before delete
        let visible = db.get_all_games().unwrap();
        assert_eq!(visible.len(), 1);
        assert_eq!(visible[0].playtime_seconds, 3600);
        assert_eq!(visible[0].rating, 8);
        assert_eq!(visible[0].play_count, 5);

        // Soft delete
        db.remove_game("my_game").unwrap();

        // Verify game is hidden from normal queries
        let visible = db.get_all_games().unwrap();
        assert!(visible.is_empty(), "Soft-deleted game should not appear in get_all_games");

        // Verify stats survive — get_game_any ignores hidden flag
        let record = db.get_game_any("my_game").expect("Soft-deleted game should still exist in DB");
        assert_eq!(record.playtime_seconds, 3600, "playtime must survive soft delete");
        assert_eq!(record.rating, 8, "rating must survive soft delete");
        assert_eq!(record.play_count, 5, "play_count must survive soft delete");
        assert_eq!(record.last_played.as_deref(), Some("2026-01-15T10:00:00Z"));
        assert!(record.hidden, "record should be marked hidden");

        // Verify dir is still in get_all_dir_keys (prevents wizard re-trigger)
        let dirs = db.get_all_dir_keys().unwrap();
        assert!(dirs.contains(&"my_game".to_string()));
    }

    #[test]
    fn test_upsert_unhides_hidden_game() {
        let (db, _dir) = temp_db();
        let mut game = make_test_game("my_game");
        db.upsert_game(&game).unwrap();

        // Hide it
        db.remove_game("my_game").unwrap();
        let record = db.get_game_any("my_game").unwrap();
        assert!(record.hidden);

        // Re-add via upsert — should unhide
        game.hidden = false;
        db.upsert_game(&game).unwrap();

        let visible = db.get_all_games().unwrap();
        assert_eq!(visible.len(), 1, "Re-upserted game should be visible again");
        assert!(!visible[0].hidden);
    }

    #[test]
    fn test_remove_game_does_not_hard_delete() {
        let (db, _dir) = temp_db();
        let game = make_test_game("my_game");
        db.upsert_game(&game).unwrap();
        db.remove_game("my_game").unwrap();

        // get_all_dir_keys should still contain the dir
        let dirs = db.get_all_dir_keys().unwrap();
        assert_eq!(dirs.len(), 1);
        assert_eq!(dirs[0], "my_game");
    }
}
