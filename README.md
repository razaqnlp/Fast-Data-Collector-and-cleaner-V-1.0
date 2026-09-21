# Fast Data Collector and Cleaner v1.1.0

A FastAPI-based data collection and cleaning pipeline for Romanized Pashto text. The app currently runs locally with API-based processing and is ready for GitHub deployment without shipping any model files.

## Latest release: v1.1.0

Version 1.1.0 is the new backward-compatible release of the original v1.0 project. It keeps the existing cleaning, language detection, sentiment analysis, and export workflow while substantially improving YouTube collection and project maintainability.

### What's new in v1.1.0

- Added structured YouTube dataset columns: `id`, `video_id`, `original_text`, and `collection_date`
- Added Excel-friendly CSV output with reliable comma-column detection
- Added duplicate YouTube video ID detection with an inline warning
- Added an explicit **I know - scrape again** action for intentional re-scraping
- Added persistent auto-download for newly scraped CSV files
- Added an opt-in custom CSV filename with collision-safe naming
- Added visible collection progress feedback and a loading spinner
- Added support for importing the generated CSV format through `original_text`
- Removed obsolete source copies, local runtime artifacts, and model files from the GitHub project

See [CHANGELOG.md](CHANGELOG.md) for the release history.

## Current status

This repository is the working local version that is already running correctly on a local computer. The model layer is not bundled in this GitHub repo yet, and the app is configured to use external APIs for now while the local model deployment is prepared.

Model deployment is planned for the next release, and the repo will be updated once the hosted or packaged model is ready.

## Features

- Collect comments from YouTube or import CSV data
- Clean comments by removing links, emojis, invalid characters, and noisy text
- Detect Romanized Pashto entries
- Classify sentiment labels for the processed dataset
- Export cleaned or labeled results as CSV
- Dark three-pane FastAPI dashboard UI
- Separate YouTube comment collection with sequential local CSV saving

## Workflow

Data collection and text processing are intentionally separate:

1. Open **Collect data**, enter a YouTube video ID, and collect the comments.
2. The collector saves a numbered file such as `youtube_comments_001.csv` in the local `collected_data` folder.
3. Open **Clean** and upload that saved CSV, or upload a CSV from another source.
4. Continue through **Detect** and **Sentiment**.

This structure leaves room for additional source collectors, such as X or other social platforms, without mixing collection controls into the processing pipeline.

## UI

The dashboard UI is served directly from the `templates/` and `static/` folders. It includes:

- Clear pipeline navigation for cleaning, Pashto detection, and sentiment
- Larger, more readable typography and form controls
- YouTube and CSV input switching with CSV drag-and-drop
- Raw and cleaned comment preview tabs
- Sentiment search, label filtering, editable labels, and CSV export
- Right-side batch, pipeline, label distribution, and API settings panels

The interface remains API-first while model deployment is prepared for a future release.

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