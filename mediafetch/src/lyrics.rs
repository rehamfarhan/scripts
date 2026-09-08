use anyhow::Result;
use id3::TagLike;
use regex::Regex;
use serde::Deserialize;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub struct LrcResponse {
    pub id: Option<u64>,
    #[serde(rename = "trackName")]
    pub track_name: Option<String>,
    #[serde(rename = "artistName")]
    pub artist_name: Option<String>,
    #[serde(rename = "plainLyrics")]
    pub plain_lyrics: Option<String>,
    #[serde(rename = "syncedLyrics")]
    pub synced_lyrics: Option<String>,
}

pub struct LyricsManager {
    client: reqwest::Client,
}

impl LyricsManager {
    pub fn new() -> Self {
        let client = reqwest::Client::builder()
            .user_agent("mediafetch/0.1.0 (https://github.com/directpass/mediafetch)")
            .timeout(std::time::Duration::from_secs(8))
            .build()
            .unwrap_or_else(|_| reqwest::Client::new());
        Self { client }
    }

    /// Cleans common video clutter from titles (e.g. "[Official Music Video]", "(Audio)", "(Lyrics)")
    pub fn clean_title(title: &str) -> String {
        let re_clutter = Regex::new(r"(?i)\s*[\(\[\{](?:official\s+)?(?:music\s+)?(?:video|audio|lyrics|hd|4k|remastered|visualizer|feat\.?.*?)[\)\]\}]").unwrap();
        let cleaned = re_clutter.replace_all(title, "");
        cleaned.trim().to_string()
    }

    /// Splits "Artist - Track" or falls back to uploader as artist
    pub fn parse_artist_and_title(raw_title: &str, uploader: &str) -> (String, String) {
        let cleaned = Self::clean_title(raw_title);
        if let Some((artist, track)) = cleaned.split_once(" - ") {
            (artist.trim().to_string(), track.trim().to_string())
        } else if let Some((artist, track)) = cleaned.split_once(" – ") {
            (artist.trim().to_string(), track.trim().to_string())
        } else {
            let uploader_clean = uploader.replace(" - Topic", "").trim().to_string();
            (uploader_clean, cleaned)
        }
    }

    /// Fetch lyrics from LRCLIB using exact match or fallback search
    pub async fn fetch_lyrics(&self, artist: &str, track: &str, duration_secs: Option<u64>) -> Result<Option<LrcResponse>> {
        // 1. Try exact match /api/get
        let mut req = self.client.get("https://lrclib.net/api/get")
            .query(&[("artist_name", artist), ("track_name", track)]);

        if let Some(dur) = duration_secs {
            let dur_str = dur.to_string();
            req = req.query(&[("duration", dur_str.as_str())]);
        }

        if let Ok(res) = req.send().await {
            if res.status().is_success() {
                if let Ok(data) = res.json::<LrcResponse>().await {
                    if data.plain_lyrics.is_some() || data.synced_lyrics.is_some() {
                        return Ok(Some(data));
                    }
                }
            }
        }

        // 2. Fallback to /api/search?q=...
        let query = format!("{} {}", artist, track);
        let search_res = self.client.get("https://lrclib.net/api/search")
            .query(&[("q", query.as_str())])
            .send()
            .await;

        if let Ok(res) = search_res {
            if res.status().is_success() {
                if let Ok(items) = res.json::<Vec<LrcResponse>>().await {
                    for item in items {
                        if item.synced_lyrics.is_some() || item.plain_lyrics.is_some() {
                            return Ok(Some(item));
                        }
                    }
                }
            }
        }

        Ok(None)
    }

    /// Writes .lrc sidecar file and embeds USLT tag if it's an MP3 file
    pub fn process_downloaded_lyrics(
        &self,
        audio_file: &Path,
        lyrics: &LrcResponse,
    ) -> Result<(bool, PathBuf)> {
        let lrc_path = audio_file.with_extension("lrc");

        // Write .lrc companion sidecar
        let lrc_content = lyrics.synced_lyrics.as_ref().or(lyrics.plain_lyrics.as_ref());
        let mut wrote_lrc = false;
        if let Some(text) = lrc_content {
            if fs::write(&lrc_path, text).is_ok() {
                wrote_lrc = true;
            }
        }

        // If MP3, embed USLT ID3 frame
        if audio_file.extension().and_then(|e| e.to_str()).map(|e| e.eq_ignore_ascii_case("mp3")).unwrap_or(false) {
            let plain = lyrics.plain_lyrics.as_ref().or(lyrics.synced_lyrics.as_ref());
            if let Some(plain_text) = plain {
                let mut tag = id3::Tag::read_from_path(audio_file).unwrap_or_else(|_| id3::Tag::new());
                tag.add_frame(id3::frame::Lyrics {
                    lang: "eng".to_string(),
                    description: "".to_string(),
                    text: plain_text.clone(),
                });
                let _ = tag.write_to_path(audio_file, id3::Version::Id3v24);
            }
        }

        Ok((wrote_lrc, lrc_path))
    }
}
