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
        cmd.args([
            "--newline",
            "--progress",
            "--progress-template",
            "download:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s|%(progress._total_bytes_str)s",
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

        // Track stderr in background for error diagnostics
        let stderr_task = tokio::spawn(async move {
            let mut err_reader = BufReader::new(stderr).lines();
            let mut last_err = String::new();
            while let Ok(Some(line)) = err_reader.next_line().await {
                if !line.trim().is_empty() {
                    last_err = line;
                }
            }
            last_err
        });

        while let Ok(Some(line)) = reader.next_line().await {
            let line = line.trim();
            if line.starts_with("download:") {
                let parts: Vec<&str> = line[9..].split('|').collect();
                if parts.len() >= 4 {
                    let percent_raw = parts[0].replace('%', "").trim().to_string();
                    let percent = percent_raw.parse::<f64>().unwrap_or(0.0);
                    let speed = parts[1].trim().to_string();
                    let eta = parts[2].trim().to_string();
                    let size = parts[3].trim().to_string();

                    let _ = tx.send(DownloadProgress::Downloading {
                        percent,
                        speed: if speed.is_empty() { "-- KiB/s".to_string() } else { speed },
                        eta: if eta.is_empty() { "--:--".to_string() } else { eta },
                        size: if size.is_empty() { "-- MiB".to_string() } else { size },
                    });
                }
            } else if line.starts_with('/') {
                // `after_move:filepath` prints the final full absolute path
                let path = PathBuf::from(line);
                if path.exists() {
                    final_file_path = Some(path);
                }
            } else if line.contains("[ExtractAudio]") || line.contains("[Merger]") || line.contains("[Fixup") {
                let _ = tx.send(DownloadProgress::ProcessingStep(line.to_string()));
            }
        }

        let status = child.wait().await.context("yt-dlp child process failed to exit")?;
        let last_stderr = stderr_task.await.unwrap_or_default();

        if !status.success() {
            let err_msg = if !last_stderr.is_empty() {
                last_stderr
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
            let title = metadata.display_title();
            let uploader = metadata.display_uploader();
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

        let summary = DownloadSummary {
            file_name: resolved_file.file_name().unwrap_or_default().to_string_lossy().to_string(),
            file_path: resolved_file,
            file_size_bytes,
            formatted_size,
            duration: start_time.elapsed(),
            preset,
            lrc_path,
            lyrics_found,
            title: metadata.display_title().to_string(),
            channel: metadata.display_uploader().to_string(),
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
        const KIB: f64 = 1024.0;
        const MIB: f64 = 1024.0 * KIB;
        const GIB: f64 = 1024.0 * MIB;

        let b = bytes as f64;
        if b >= GIB {
            format!("{:.2} GiB", b / GIB)
        } else if b >= MIB {
            format!("{:.1} MiB", b / MIB)
        } else if b >= KIB {
            format!("{:.0} KiB", b / KIB)
        } else {
            format!("{} B", bytes)
        }
    }
}
