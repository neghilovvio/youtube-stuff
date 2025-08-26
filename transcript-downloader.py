from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
import requests
import re
import os
from urllib.parse import urlparse, parse_qs

def get_video_id(youtube_url):
    """
    Extract the video ID from a YouTube URL.
    Args:
        youtube_url (str): The YouTube URL.
    Returns:
        str: The extracted video ID or None if not found.
    """
    # Normalize and parse
    url = youtube_url.strip()
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or '').lower()
        path = parsed.path or ''
        query = parse_qs(parsed.query)

        # youtu.be/<id>
        if 'youtu.be' in host:
            parts = [p for p in path.split('/') if p]
            if parts:
                candidate = parts[0]
                return candidate[:11] if len(candidate) >= 11 else None

        # youtube.com/watch?v=<id>
        if 'youtube.com' in host or 'm.youtube.com' in host or 'www.youtube.com' in host:
            if 'v' in query and query['v']:
                candidate = query['v'][0]
                return candidate[:11] if len(candidate) >= 11 else None

            # /shorts/<id>
            if path.startswith('/shorts/'):
                candidate = path.split('/shorts/', 1)[1].split('/')[0]
                return candidate[:11] if len(candidate) >= 11 else None

            # /embed/<id> or /v/<id>
            for prefix in ('/embed/', '/v/'):
                if path.startswith(prefix):
                    candidate = path.split(prefix, 1)[1].split('/')[0]
                    return candidate[:11] if len(candidate) >= 11 else None

        # Fallback regex for uncommon patterns
        pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/\S*?[?&]v=|youtu\.be\/)([a-zA-Z0-9_-]{11})'
        match = re.search(pattern, url)
        return match.group(1) if match else None
    except Exception:
        return None

def get_video_title(video_id):
    """
    Get the title of the YouTube video.
    Args:
        video_id (str): The YouTube video ID.
    Returns:
        str: The title of the video or "Unknown" if not found.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        matches = re.findall(r'<title>(.*?)</title>', response.text)
        return matches[0].replace(" - YouTube", "") if matches else "Unknown"
    except requests.RequestException as e:
        print(f"Error fetching video title: {e}")
        return "Unknown"

def download_transcript(video_id):
    """
    Download the transcript and return as a string.
    Args:
        video_id (str): The YouTube video ID.
    Returns:
        str: The transcript text or an empty string if an error occurs.
    """
    try:
        # API v1.2.2 uses an instance with list() and fetch().
        # Try to prefer manual transcripts; fall back to generated; finally direct fetch.
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
            # Fallback to shortcut fetch
            entries = ytt_api.fetch(video_id, languages=preferred_langs)

        formatter = TextFormatter()
        transcript_text = formatter.format_transcript(entries)

        # Remove timecodes and speaker names
        transcript_text = re.sub(r'\[\d+:\d+:\d+\]', '', transcript_text)
        transcript_text = re.sub(r'<\w+>', '', transcript_text)
        return transcript_text
    except Exception as e:
        print(f"Error downloading transcript: {e}")
        return ""

def main():
    youtube_url = input("Enter the YouTube video link: ")
    video_id = get_video_id(youtube_url)

    if video_id:
        transcript_text = download_transcript(video_id)
        if transcript_text:
            video_title = get_video_title(video_id)
            file_name = f"{video_id}_{video_title}.txt"
            file_name = re.sub(r'[\\/*?:"<>|]', '', file_name)  # Remove invalid characters

            out_dir = "transcript-downloads"
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, file_name)

            with open(out_path, 'w', encoding='utf-8') as file:
                file.write(transcript_text)

            print(f"Transcript saved to {out_path}")
        else:
            print("Unable to download transcript.")
    else:
        print("Invalid YouTube URL.")

if __name__ == "__main__":
    main()