use std::path::PathBuf;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PresetType {
    Video,
    Music,
    Flac,
    Shorts,
    Podcast,
    Archive,
}

impl PresetType {
    pub const ALL: [PresetType; 6] = [
        PresetType::Video,
        PresetType::Music,
        PresetType::Flac,
        PresetType::Shorts,
        PresetType::Podcast,
        PresetType::Archive,
    ];

    pub fn from_str_loose(s: &str) -> Option<Self> {
        match s.to_lowercase().trim() {
            "video" | "v" | "default" => Some(PresetType::Video),
            "music" | "audio" | "m" | "mp3" | "a" => Some(PresetType::Music),
            "flac" | "lossless" => Some(PresetType::Flac),
            "shorts" | "short" | "reel" | "tiktok" => Some(PresetType::Shorts),
            "podcast" | "pod" | "opus" => Some(PresetType::Podcast),
            "archive" | "arch" | "max" | "best" => Some(PresetType::Archive),
            _ => None,
        }
    }

    pub fn title(&self) -> &'static str {
        match self {
            PresetType::Video => "Video",
            PresetType::Music => "Music (MP3)",
            PresetType::Flac => "FLAC",
            PresetType::Shorts => "Shorts",
            PresetType::Podcast => "Podcast",
            PresetType::Archive => "Archive",
        }
    }

    pub fn badge(&self) -> &'static str {
        match self {
            PresetType::Video => "1080p MKV",
            PresetType::Music => "320k MP3 + Lyrics",
            PresetType::Flac => "Lossless + Lyrics",
            PresetType::Shorts => "9:16 Vertical MP4",
            PresetType::Podcast => "Opus Audio",
            PresetType::Archive => "Max Quality Video",
        }
    }

    pub fn description(&self) -> &'static str {
        match self {
            PresetType::Video => "1080p H.265 MKV video, embeds PNG thumbnail, merges English subtitles (en.*)",
            PresetType::Music => "High quality MP3 (320k), square album art, auto LRCLIB lyrics & .lrc sidecar",
            PresetType::Flac => "Lossless FLAC audio, square album art, embedded lyrics & .lrc sidecar",
            PresetType::Shorts => "1080p MP4 optimized for 9:16 vertical video formats (Shorts, Reels, TikTok)",
            PresetType::Podcast => "Audio-only Opus format, embeds metadata and thumbnail",
            PresetType::Archive => "Maximum quality video/audio preservation with all available subtitles",
        }
    }

    pub fn icon(&self) -> &'static str {
        match self {
            PresetType::Video => "🎬",
            PresetType::Music => "🎵",
            PresetType::Flac => "🎧",
            PresetType::Shorts => "📱",
            PresetType::Podcast => "🎙️",
            PresetType::Archive => "📦",
        }
    }

    pub fn target_directory(&self) -> PathBuf {
        let home = dirs::home_dir().unwrap_or_else(|| PathBuf::from("/home/directpass"));
        match self {
            PresetType::Video | PresetType::Shorts | PresetType::Archive => {
                home.join("Videos").join("Downloads")
            }
            PresetType::Music | PresetType::Flac | PresetType::Podcast => {
                home.join("Music").join("Downloads")
            }
        }
    }

    pub fn extra_args(&self) -> Vec<&'static str> {
        match self {
            PresetType::Video => vec![
                "-f", "bv*[height<=1080]+ba/b[height<=1080]/b",
                "--merge-output-format", "mkv",
                "--embed-thumbnail",
                "--embed-subs",
                "--sub-langs", "en.*",
            ],
            PresetType::Music => vec![
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "320k",
                "--convert-thumbnails", "png",
                "--ppa", "thumbnailsconvertor:-vf crop=ih:ih",
                "--embed-thumbnail",
                "--embed-metadata",
            ],
            PresetType::Flac => vec![
                "-x",
                "--audio-format", "flac",
                "--convert-thumbnails", "png",
                "--ppa", "thumbnailsconvertor:-vf crop=ih:ih",
                "--embed-thumbnail",
                "--embed-metadata",
            ],
            PresetType::Shorts => vec![
                "-f", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
                "--merge-output-format", "mp4",
                "--embed-thumbnail",
            ],
            PresetType::Podcast => vec![
                "-x",
                "--audio-format", "opus",
                "--embed-thumbnail",
                "--embed-metadata",
            ],
            PresetType::Archive => vec![
                "-f", "bv*+ba/b",
                "--all-subs",
                "--embed-subs",
                "--embed-thumbnail",
                "--embed-metadata",
            ],
        }
    }

    pub fn should_fetch_lyrics(&self) -> bool {
        matches!(self, PresetType::Music | PresetType::Flac)
    }

    pub fn container_format(&self) -> &'static str {
        match self {
            PresetType::Video => "Matroska (.mkv)",
            PresetType::Music => "MPEG Audio (.mp3 @ 320k CBR)",
            PresetType::Flac => "Free Lossless Audio (.flac)",
            PresetType::Shorts => "MPEG-4 (.mp4)",
            PresetType::Podcast => "Ogg Opus (.opus)",
            PresetType::Archive => "Best Available Container",
        }
    }

    pub fn video_spec(&self) -> &'static str {
        match self {
            PresetType::Video => "1080p Max (H.265 / HEVC preferred)",
            PresetType::Music => "N/A (Audio extraction)",
            PresetType::Flac => "N/A (Lossless audio extraction)",
            PresetType::Shorts => "1080p Max (9:16 Vertical Video)",
            PresetType::Podcast => "N/A (Audio extraction)",
            PresetType::Archive => "Unconstrained Source Max (4K/8K)",
        }
    }

    pub fn audio_spec(&self) -> &'static str {
        match self {
            PresetType::Video => "Best source audio stream merged",
            PresetType::Music => "320 kbps High Quality CBR",
            PresetType::Flac => "Bit-perfect lossless stream",
            PresetType::Shorts => "AAC / M4A stereo stream",
            PresetType::Podcast => "Opus high-efficiency speech/music",
            PresetType::Archive => "Uncompressed best audio stream",
        }
    }

    pub fn subtitles_policy(&self) -> &'static str {
        match self {
            PresetType::Video => "English (en.*) merged as soft subs",
            PresetType::Music => "N/A (Embedded lyrics used instead)",
            PresetType::Flac => "N/A (Embedded lyrics used instead)",
            PresetType::Shorts => "None (Hardcoded on video stream)",
            PresetType::Podcast => "N/A",
            PresetType::Archive => "All available subtitles embedded",
        }
    }

    pub fn thumbnail_policy(&self) -> &'static str {
        match self {
            PresetType::Video => "Embedded PNG cover attachment",
            PresetType::Music => "1:1 Square cropped (crop=ih:ih, PNG, ID3 APIC)",
            PresetType::Flac => "1:1 Square cropped (crop=ih:ih, PNG, Vorbis Picture)",
            PresetType::Shorts => "9:16 Vertical video thumbnail",
            PresetType::Podcast => "Embedded podcast cover thumbnail",
            PresetType::Archive => "Full resolution original thumbnail",
        }
    }

    pub fn lyrics_policy(&self) -> &'static str {
        match self {
            PresetType::Music => "Auto LRCLIB (ID3 USLT frame + .lrc sidecar)",
            PresetType::Flac => "Auto LRCLIB (Vorbis comments + .lrc sidecar)",
            _ => "N/A",
        }
    }
}
