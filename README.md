# Fast Data Collector and Cleaner V1.0

A FastAPI-based data collection and cleaning pipeline for Romanized Pashto text. The app currently runs locally with API-based processing and is ready for GitHub deployment without shipping any model files.

## Current status

This repository is the working local version that is already running correctly on a local computer. The model layer is not bundled in this GitHub repo yet, and the app is configured to use external APIs for now while the local model deployment is prepared.

Model deployment is planned for the next release, and the repo will be updated once the hosted or packaged model is ready.

## Features

- Collect comments from YouTube or import CSV data
- Clean comments by removing links, emojis, invalid characters, and noisy text
- Detect Romanized Pashto entries
- Classify sentiment labels for the processed dataset
- Export cleaned or labeled results as CSV
- Simple FastAPI dashboard UI

## Requirements

- Python 3.10 or newer
- A YouTube Data API v3 key for YouTube input
- API access for the current external model/detection workflow

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8000 in the browser.

## API-first usage

Because the model files are not included in this public repo yet, the app is designed to use APIs for the current local working setup. This means the app is ready to run on a local machine without shipping model binaries or heavy ML assets.

When model deployment is complete, the repository will be updated to include the appropriate packaged or hosted model configuration.

## Notes

- Model files such as `.bin`, `.model`, `*.pt`, and similar artifacts are intentionally ignored and are not pushed to GitHub.
- The app is working locally and is being prepared for deployment in stages.
- The project should be treated as an API-first build until the full model deployment is ready.

## CSV input

Upload a CSV containing a comment column. If a matching comment column is not found, the app falls back to the first usable column automatically.