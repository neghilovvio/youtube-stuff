import os
import sys
import json
from pathlib import Path
from typing import Tuple

from openai import OpenAI
from dotenv import load_dotenv


def load_transcript(path: Path) -> str:
    """
    Load transcript text from file.

    Args:
        path (Path): Path to the transcript file.

    Returns:
        str: Transcript content.
    """
    return path.read_text(encoding="utf-8").strip()


def build_youtube_prompt(transcript: str) -> str:
    """
    Build prompt to generate a YouTube SEO title and description with tags.

    Args:
        transcript (str): Transcript text.

    Returns:
        str: Prompt string.
    """
    return (
        "You are an expert YouTube content strategist and SEO copywriter.\n"
        "Given the transcript below, craft: \n"
        "1) A punchy, curiosity-driven YouTube TITLE (max ~80 chars, no clickbait).\n"
        "2) An SEO-optimized DESCRIPTION (150-300 words) with:\n"
        "   - a compelling hook in the first sentence,\n"
        "   - a concise summary with clear value,\n"
        "   - 5-8 keyword phrases (bold them),\n"
        "   - 5-10 relevant hashtags at the end.\n"
        "Return valid JSON with keys: title, description.\n\n"
        f"Transcript:\n{transcript}\n"
    )


def build_linkedin_prompt(transcript: str) -> str:
    """
    Build prompt to generate a LinkedIn post with an ironic, engaging tone.

    Args:
        transcript (str): Transcript text.

    Returns:
        str: Prompt string.
    """
    return (
        "You are a seasoned LinkedIn copywriter with a witty, slightly ironic tone.\n"
        "Write a single LinkedIn post (120-220 words) based on the transcript below.\n"
        "Guidelines:\n"
        "- Hook in the first 1-2 lines.\n"
        "- Be insightful, practical, and a bit playful (no cringe).\n"
        "- Short paragraphs and line breaks for readability.\n"
        "- Add 4-8 relevant hashtags at the end.\n"
        "- No emojis overload; use sparingly (0-2).\n"
        "Return plain text only.\n\n"
        f"Transcript:\n{transcript}\n"
    )


def call_openai(client: OpenAI, model: str, system_prompt: str, user_prompt: str) -> str:
    """
    Call OpenAI Chat Completions API and return the text content.

    Args:
        client (OpenAI): OpenAI client instance.
        model (str): Model name, e.g., gpt-4o-mini.
        system_prompt (str): System role message.
        user_prompt (str): User content prompt.

    Returns:
        str: Assistant text content.
    """
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


def generate_youtube_content(client: OpenAI, model: str, transcript: str) -> Tuple[str, str]:
    """
    Generate YouTube title and description from transcript.

    Args:
        client (OpenAI): OpenAI client.
        model (str): Model name.
        transcript (str): Transcript text.

    Returns:
        Tuple[str, str]: (title, description)
    """
    system_msg = "You write high-converting YouTube SEO content."
    user_msg = build_youtube_prompt(transcript)
    text = call_openai(client, model, system_msg, user_msg)

    # Try to parse JSON; if it fails, return as best-effort
    try:
        data = json.loads(text)
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        if not title or not description:
            raise ValueError("Missing fields in JSON")
        return title, description
    except Exception:
        # Fallback: best-effort split
        return text.split("\n", 1)[0][:80], text


def generate_linkedin_post(client: OpenAI, model: str, transcript: str) -> str:
    """
    Generate a LinkedIn post text from transcript.

    Args:
        client (OpenAI): OpenAI client.
        model (str): Model name.
        transcript (str): Transcript text.

    Returns:
        str: LinkedIn post content.
    """
    system_msg = "You write engaging LinkedIn posts for tech and business audiences."
    user_msg = build_linkedin_prompt(transcript)
    return call_openai(client, model, system_msg, user_msg)


def main() -> None:
    """
    Generate platform content from a transcript file.

    Usage:
        python content_generator.py <transcript_path> [--model gpt-4o-mini]

    Outputs are written next to the transcript file:
        - <base>_youtube_title.txt
        - <base>_youtube_description.txt
        - <base>_linkedin_post.md
    """
    if len(sys.argv) < 2:
        print("Usage: python content_generator.py <transcript_path> [--model gpt-4o-mini] [--print]")
        sys.exit(1)

    transcript_path = Path(sys.argv[1]).expanduser().resolve()
    if not transcript_path.exists():
        print(f"❌ File not found: {transcript_path}")
        sys.exit(2)

    # Load .env first so environment variables from file are available
    load_dotenv()

    # Model selection
    default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    model = default_model
    # Simple arg parsing for optional flags
    args = sys.argv[1:]
    print_to_stdout = "--print" in args

    if "--model" in args:
        try:
            model_idx = args.index("--model")
            model = args[model_idx + 1]
        except Exception:
            pass

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY environment variable is not set.")
        sys.exit(3)

    client = OpenAI(api_key=api_key)

    transcript = load_transcript(transcript_path)

    print("🧠 Generating LinkedIn post...")
    li_post = generate_linkedin_post(client, model, transcript)

    base = transcript_path.with_suffix("")
    li_path = base.parent / f"{base.name}_linkedin_post.md"

    li_path.write_text(li_post, encoding="utf-8")

    print("✅ Done. Files written:")
    print(f" - {li_path}")

    if print_to_stdout:
        print("\n================ COPY FOR LINKEDIN (POST) ================")
        print(li_post)


if __name__ == "__main__":
    main()
