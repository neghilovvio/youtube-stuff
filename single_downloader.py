import os
import re
import sys
import subprocess
from typing import Optional

from yt_dlp import YoutubeDL
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter


def _sanitize_name(name: str) -> str:
    """
    Sanitize a string for safe filesystem usage.

    Args:
        name (str): Input name.

    Returns:
        str: Sanitized name without illegal characters.
    """
    # Remove characters not allowed on common filesystems
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Limit length to avoid OS limits
    return name[:150]


def _get_video_info(url: str) -> Optional[dict]:
    """
    Extract video info (id, title) without downloading.

    Args:
        url (str): YouTube video URL.

    Returns:
        Optional[dict]: Info dict from yt-dlp or None on failure.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'noplaylist': True,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get('_type') == 'playlist':
                # If a playlist was passed by mistake, try to select first entry
                entries = info.get('entries') or []
                if entries:
                    return entries[0]
            return info
    except Exception:
        return None


def _download_video(url: str, out_dir: str) -> None:
    """
    Download a single YouTube video as MP4 to the provided directory.

    Args:
        url (str): YouTube video URL.
        out_dir (str): Output directory for the video file.
    """
    os.makedirs(out_dir, exist_ok=True)

    ydl_opts = {
        'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best',
        'ignoreerrors': False,
        'no_warnings': False,
        'extract_flat': False,
        'postprocessors': [
            {
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }
        ],
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'outtmpl': os.path.join(out_dir, '%(title)s.%(ext)s'),
        'retries': 3,
        'fragment_retries': 3,
        'clean_infojson': True,
        'keepvideo': False,
    }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def _download_transcript(video_id: str) -> str:
    """
    Download the transcript for a given video ID.

    Args:
        video_id (str): YouTube video ID.

    Returns:
        str: Transcript text (empty string if unavailable).
    """
    try:
        preferred_langs = ['en', 'en-US', 'en-GB']
        ytt_api = YouTubeTranscriptApi()

        try:
            transcript_list = ytt_api.list(video_id)
            try:
                transcript = transcript_list.find_manually_created_transcript(preferred_langs)
            except Exception:
                transcript = transcript_list.find_generated_transcript(preferred_langs)
            entries = transcript.fetch()
        except Exception:
            entries = ytt_api.fetch(video_id, languages=preferred_langs)

        formatter = TextFormatter()
        transcript_text = formatter.format_transcript(entries)
        transcript_text = re.sub(r'\[\d+:\d+:\d+\]', '', transcript_text)
        transcript_text = re.sub(r'<\w+>', '', transcript_text)
        return transcript_text
    except Exception:
        return ""


def main() -> None:
    """
    Download both video and transcript for a single YouTube URL.

    Usage:
        python single_downloader.py <youtube_url> [output_base_dir]

    Args:
        None: Uses sys.argv for inputs.
    """
    if len(sys.argv) < 2:
        print("Usage: python single_downloader.py <youtube_url> [output_base_dir]")
        sys.exit(1)

    url = sys.argv[1].strip()
    base_out = sys.argv[2].strip() if len(sys.argv) >= 3 else os.path.join(os.getcwd(), 'downloads')

    info = _get_video_info(url)
    if not info:
        print("❌ Could not extract video information. Is the URL valid?")
        sys.exit(2)

    video_id = info.get('id') or ''
    title = info.get('title') or 'video'

    folder_name = _sanitize_name(f"{video_id}_{title}") if video_id else _sanitize_name(title)
    target_dir = os.path.join(base_out, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    print(f"📁 Output directory: {target_dir}")

    # 1) Download video
    print("🎥 Downloading video...")
    _download_video(url, target_dir)
    print("✅ Video downloaded.")

    # 2) Download transcript
    if video_id:
        print("📝 Fetching transcript...")
        transcript = _download_transcript(video_id)
        if transcript:
            transcript_path = os.path.join(target_dir, f"{folder_name}.txt")
            with open(transcript_path, 'w', encoding='utf-8') as f:
                f.write(transcript)
            print(f"✅ Transcript saved to {transcript_path}")

            # Auto-generate content using content_generator.py
            generator_script = os.path.join(os.path.dirname(__file__), 'content_generator.py')
            if os.path.exists(generator_script):
                print("🧩 Avvio content_generator per creare il post LinkedIn...")
                try:
                    # Reason: use the same interpreter and pass transcript path; content_generator handles model/env
                    result = subprocess.run(
                        [sys.executable, generator_script, transcript_path],
                        cwd=os.path.dirname(generator_script),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=False,
                    )
                    print(result.stdout)
                    if result.returncode == 0:
                        print("✅ Contenuti generati con successo.")
                    else:
                        print(f"⚠️ content_generator è terminato con codice {result.returncode}.")
                except Exception as e:
                    print(f"❌ Errore nell'esecuzione di content_generator: {e}")
            else:
                print("⚠️ content_generator.py non trovato: salta generazione contenuti.")
        else:
            print("⚠️ Transcript not available for this video.")
    else:
        print("⚠️ Could not resolve a video ID for transcript retrieval.")

    print("🎉 Done.")


if __name__ == '__main__':
    main()
