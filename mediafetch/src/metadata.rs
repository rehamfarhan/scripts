use anyhow::{Context, Result};
use serde::Deserialize;
use tokio::process::Command;

#[derive(Debug, Clone, Deserialize, Default)]
#[allow(dead_code)]
pub struct MediaMetadata {
    pub id: Option<String>,
    pub title: Option<String>,
    pub uploader: Option<String>,
    pub channel: Option<String>,
    pub duration: Option<f64>,
    pub view_count: Option<u64>,
    pub upload_date: Option<String>,
    pub thumbnail: Option<String>,
    pub webpage_url: Option<String>,
}

impl MediaMetadata {
    pub async fn fetch(url: &str) -> Result<Self> {
        let output = Command::new("yt-dlp")
            .args([
                "--dump-single-json",
                "--no-playlist",
                "--skip-download",
                url,
            ])
            .output()
            .await
            .context("Failed to run yt-dlp to inspect stream")?;

        if !output.status.success() {
            let err = String::from_utf8_lossy(&output.stderr);
            anyhow::bail!("yt-dlp error: {}", err.trim());
        }

        let json_str = String::from_utf8_lossy(&output.stdout);
        let meta: MediaMetadata = serde_json::from_str(&json_str)
            .context("Failed to parse yt-dlp JSON metadata")?;

        Ok(meta)
    }

    pub fn display_title(&self) -> &str {
        self.title.as_deref().unwrap_or("Unknown Title")
    }

    pub fn display_uploader(&self) -> &str {
        self.channel
            .as_deref()
            .or(self.uploader.as_deref())
            .unwrap_or("Unknown Creator")
    }

    pub fn formatted_duration(&self) -> String {
        match self.duration {
            Some(d) if d > 0.0 => {
                let total_secs = d as u64;
                let hours = total_secs / 3600;
                let minutes = (total_secs % 3600) / 60;
                let seconds = total_secs % 60;
                if hours > 0 {
                    format!("{:02}:{:02}:{:02}", hours, minutes, seconds)
                } else {
                    format!("{:02}:{:02}", minutes, seconds)
                }
            }
            _ => "--:--".to_string(),
        }
    }

    pub fn formatted_views(&self) -> String {
        match self.view_count {
            Some(v) if v >= 1_000_000 => format!("{:.1}M views", v as f64 / 1_000_000.0),
            Some(v) if v >= 1_000 => format!("{:.1}K views", v as f64 / 1_000.0),
            Some(v) => format!("{} views", v),
            None => "-- views".to_string(),
        }
    }

    pub fn formatted_date(&self) -> String {
        if let Some(ref d) = self.upload_date {
            if d.len() == 8 {
                return format!("{}-{}-{}", &d[0..4], &d[4..6], &d[6..8]);
            }
        }
        "Recent".to_string()
    }
}
