uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv run python video-downloader.py
uv run python transcript-downloader.py
deactivate

uv run python content_generator.py "downloads/robot_workers/robot_workers.txt"


uv run python repeat_visit.py --url "https://youtube.com/shorts/G8gDaYNPDcs"  --views 1 --browser chrome --watch-until-end --progress --headless

uv run python repeat_visit.py --url "https://www.youtube.com/watch?v=B04b1czi0WM"  --views 1 --browser chrome --watch-until-end --progress 

