uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv run python video-downloader.py
uv run python transcript-downloader.py
deactivate