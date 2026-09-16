use crate::lyrics::LyricsManager;
use crate::metadata::MediaMetadata;
use crate::presets::PresetType;
use anyhow::{Context, Result};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::{Duration, Instant};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio::sync::mpsc::UnboundedSender;

#[derive(Debug, Clone)]
#[allow(dead_code)]
pub enum DownloadProgress {
    ResolvingMetadata,
    MetadataLoaded(MediaMetadata),
    MetadataFailed(String),
    Downloading {
        percent: f64,
        speed: String,
        eta: String,
        size: String,
    },
    ProcessingStep(String),
    Complete(DownloadSummary),
    Failed(String),
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
pub struct DownloadSummary {
    pub file_path: PathBuf,
    pub file_name: String,
    pub file_size_bytes: u64,
    pub formatted_size: String,
    pub duration: Duration,
    pub speed: String,
    pub preset: PresetType,
    pub lrc_path: Option<PathBuf>,
    pub lyrics_found: bool,
    pub title: String,
    pub channel: String,
}

pub struct Downloader;

impl Downloader {
    pub async fn run(
        url: String,
        preset: PresetType,
        metadata: MediaMetadata,
        tx: UnboundedSender<DownloadProgress>,
    ) -> Result<()> {
        let start_time = Instant::now();
        let target_dir = preset.target_directory();
        if !target_dir.exists() {
            fs::create_dir_all(&target_dir).context("Failed to create download directory")?;
        }

        let _ = tx.send(DownloadProgress::ProcessingStep("Spawning yt-dlp worker...".to_string()));

        let mut cmd = Command::new("yt-dlp");
        cmd.kill_on_drop(true);
        cmd.args([
            "--newline",
            "--no-playlist",
            "--no-warnings",
            "--progress",
            "--progress-template",
            "download:mediafetch:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress._total_bytes_str)s",
            "--print",
            "before_dl:title:%(title)s",
            "--print",
            "before_dl:uploader:%(uploader)s",
            "--print",
            "after_move:filepath",
            "--paths",
            target_dir.to_str().unwrap(),
            "-o",
            "%(title)s.%(ext)s",
        ]);

        for arg in preset.extra_args() {
            cmd.arg(arg);
        }
        cmd.arg(&url);

        cmd.stdout(Stdio::piped());
        cmd.stderr(Stdio::piped());

        let mut child = cmd.spawn().context("Failed to spawn yt-dlp")?;
        let stdout = child.stdout.take().context("Failed to open child stdout")?;
        let stderr = child.stderr.take().context("Failed to open child stderr")?;

        let mut reader = BufReader::new(stdout).lines();
        let mut final_file_path: Option<PathBuf> = None;
        let mut resolved_title = String::new();
        let mut resolved_uploader = String::new();
        let mut last_speed = String::from("0.0 MB/s");

        // Track stderr in background for error diagnostics
        let stderr_task = tokio::spawn(async move {
            let mut err_reader = BufReader::new(stderr).lines();
            let mut err_lines = Vec::new();
            while let Ok(Some(line)) = err_reader.next_line().await {
                let trimmed = line.trim();
                if !trimmed.is_empty() {
                    err_lines.push(trimmed.to_string());
                }
            }
            if err_lines.is_empty() {
                String::new()
            } else {
                err_lines.join("\n")
            }
        });

        let mut stream_count: usize = 0;
        let mut max_percent: f64 = 0.0;
        let is_multi_stream = matches!(preset, PresetType::Video | PresetType::Shorts | PresetType::Archive);

        while let Ok(Some(line)) = reader.next_line().await {
            let line = line.trim();
            if let Some(t) = line.strip_prefix("title:") {
                resolved_title = t.trim().to_string();
                let _ = tx.send(DownloadProgress::ProcessingStep(format!("Discovered: {}", resolved_title)));
            } else if let Some(u) = line.strip_prefix("uploader:") {
                resolved_uploader = u.trim().to_string();
            } else if let Some(rest) = line.strip_prefix("mediafetch:") {
                let parts: Vec<&str> = rest.trim().split('|').collect();
                if parts.len() >= 4 {
                    let percent_raw = parts[0].replace('%', "").trim().to_string();
                    let raw_percent = percent_raw.parse::<f64>().unwrap_or(0.0);
                    let speed = parts[1].trim().to_string();
                    let eta = parts[2].trim().to_string();
                    let size = parts[3].trim().to_string();

                    if !speed.is_empty() && speed != "-- KiB/s" && speed != "NA" {
                        last_speed = speed.clone();
                    }

                    // Multi-stream percentage smoothing (video ~85%, audio ~15%)
                    let display_percent = if is_multi_stream {
                        if raw_percent < 5.0 && max_percent > 80.0 {
                            stream_count = 1; // Switched to audio stream
                        }
                        if stream_count == 0 {
                            let p = raw_percent * 0.85;
                            if p > max_percent { max_percent = p; }
                            max_percent
                        } else {
                            let p = 85.0 + (raw_percent * 0.15);
                            if p > max_percent { max_percent = p; }
                            max_percent
                        }
                    } else {
                        raw_percent
                    };

                    let _ = tx.send(DownloadProgress::Downloading {
                        percent: display_percent.min(100.0),
                        speed: if speed.is_empty() || speed == "NA" { "-- KiB/s".to_string() } else { speed },
                        eta: if eta.is_empty() || eta == "NA" { "--:--".to_string() } else { eta },
                        size: if size.is_empty() || size == "NA" { "-- MiB".to_string() } else { size },
                    });
                }
            } else if line.starts_with('/') {
                // `after_move:filepath` prints the final full absolute path
                final_file_path = Some(PathBuf::from(line));
            } else if line.contains("[ExtractAudio]") {
                let _ = tx.send(DownloadProgress::ProcessingStep("Extracting audio stream...".to_string()));
            } else if line.contains("[Merger]") {
                let _ = tx.send(DownloadProgress::ProcessingStep("Merging video and audio streams (ffmpeg)...".to_string()));
            } else if line.contains("[ThumbnailsConvertor]") {
                let _ = tx.send(DownloadProgress::ProcessingStep("Converting and cropping thumbnail...".to_string()));
            } else if line.contains("[EmbedThumbnail]") {
                let _ = tx.send(DownloadProgress::ProcessingStep("Embedding thumbnail art...".to_string()));
            } else if line.contains("[Metadata]") {
                let _ = tx.send(DownloadProgress::ProcessingStep("Embedding media metadata tags...".to_string()));
            } else if line.contains("[Fixup") {
                let _ = tx.send(DownloadProgress::ProcessingStep("Applying container fixups...".to_string()));
            }
        }

        let status = child.wait().await.context("yt-dlp child process failed to exit")?;
        let full_stderr = stderr_task.await.unwrap_or_default();

        if !status.success() {
            let err_msg = if !full_stderr.is_empty() {
                // Pick error line or full stderr
                if let Some(err_line) = full_stderr.lines().find(|l| l.contains("ERROR:")) {
                    err_line.to_string()
                } else {
                    full_stderr.lines().last().unwrap_or(&full_stderr).to_string()
                }
            } else {
                format!("yt-dlp process exited with code {:?}", status.code())
            };
            let _ = tx.send(DownloadProgress::Failed(err_msg.clone()));
            anyhow::bail!(err_msg);
        }

        // Fallback detection if yt-dlp didn't print filepath
        let resolved_file = if let Some(p) = final_file_path {
            p
        } else {
            // Find most recently modified file in target_dir
            Self::find_latest_file(&target_dir)?
        };

        let file_size_bytes = fs::metadata(&resolved_file).map(|m| m.len()).unwrap_or(0);
        let formatted_size = Self::format_bytes(file_size_bytes);

        // LRCLIB tagging phase
        let mut lyrics_found = false;
        let mut lrc_path: Option<PathBuf> = None;

        if preset.should_fetch_lyrics() {
            let _ = tx.send(DownloadProgress::ProcessingStep("Querying LRCLIB for synced lyrics...".to_string()));
            let lyrics_mgr = LyricsManager::new();
            let title = if !resolved_title.is_empty() {
                &resolved_title
            } else if !metadata.display_title().is_empty() && metadata.display_title() != "Unknown Title" {
                metadata.display_title()
            } else {
                resolved_file.file_stem().and_then(|s| s.to_str()).unwrap_or("Unknown")
            };

            let uploader = if !resolved_uploader.is_empty() {
                &resolved_uploader
            } else if !metadata.display_uploader().is_empty() && metadata.display_uploader() != "Unknown Creator" {
                metadata.display_uploader()
            } else {
                ""
            };

            let (artist, track) = LyricsManager::parse_artist_and_title(title, uploader);
            let duration_secs = metadata.duration.map(|d| d as u64);

            if let Ok(Some(lyrics)) = lyrics_mgr.fetch_lyrics(&artist, &track, duration_secs).await {
                lyrics_found = true;
                let _ = tx.send(DownloadProgress::ProcessingStep("Embedding USLT tags & writing .lrc sidecar...".to_string()));
                if let Ok((_wrote_lrc, sidecar)) = lyrics_mgr.process_downloaded_lyrics(&resolved_file, &lyrics) {
                    lrc_path = Some(sidecar);
                }
            }
        }

        let final_title = if !resolved_title.is_empty() {
            resolved_title
        } else if !metadata.display_title().is_empty() && metadata.display_title() != "Unknown Title" {
            metadata.display_title().to_string()
        } else {
            resolved_file.file_stem().unwrap_or_default().to_string_lossy().to_string()
        };

        let final_channel = if !resolved_uploader.is_empty() {
            resolved_uploader
        } else if !metadata.display_uploader().is_empty() && metadata.display_uploader() != "Unknown Creator" {
            metadata.display_uploader().to_string()
        } else {
            "Unknown Creator".to_string()
        };

        let summary = DownloadSummary {
            file_name: resolved_file.file_name().unwrap_or_default().to_string_lossy().to_string(),
            file_path: resolved_file,
            file_size_bytes,
            formatted_size,
            duration: start_time.elapsed(),
            speed: last_speed,
            preset,
            lrc_path,
            lyrics_found,
            title: final_title,
            channel: final_channel,
        };

        let _ = tx.send(DownloadProgress::Complete(summary));
        Ok(())
    }

    fn find_latest_file(dir: &Path) -> Result<PathBuf> {
        let mut latest_path = None;
        let mut latest_time = std::time::SystemTime::UNIX_EPOCH;

        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                if let Ok(meta) = entry.metadata() {
                    if meta.is_file() {
                        if let Ok(modified) = meta.modified() {
                            if modified > latest_time {
                                latest_time = modified;
                                latest_path = Some(entry.path());
                            }
                        }
                    }
                }
            }
        }

        latest_path.context("Could not determine downloaded file path")
    }

    pub fn format_bytes(bytes: u64) -> String {
        const KB: f64 = 1000.0;
        const MB: f64 = 1000.0 * KB;
        const GB: f64 = 1000.0 * MB;

        let b = bytes as f64;
        if b >= GB {
            format!("{:.1} GB", b / GB)
        } else if b >= MB {
            format!("{:.1} MB", b / MB)
        } else if b >= KB {
            format!("{:.0} KB", b / KB)
        } else {
            format!("{} B", bytes)
        }
    }
}
