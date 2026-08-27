# Romanized Pashto Sentiment Analyzer

A FastAPI app for collecting YouTube comments or uploading a CSV, cleaning Romanized Pashto text, classifying sentiment, and exporting CSV or Excel results.

## Requirements

- Python 3.10 or newer
- A YouTube Data API v3 key for YouTube input
- A Groq or Gemini key for FreeFlow, or an OpenAI key for ChatGPT mode
- Windows Credential Manager for secure local API-key storage

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FLASK_SECRET_KEY = "replace-with-a-long-random-value"
python app.py
```

Open http://127.0.0.1:5000.

## Security

Enter API keys through the in-app Settings panel. On Windows, `keyring` stores them in Windows Credential Manager. Keys are never written to the repository or rendered back into the browser. Blank fields keep existing stored keys unchanged.

The app defaults to localhost and uses Uvicorn's development server. Set `FLASK_SECRET_KEY` before use and use a production ASGI server plus authentication before exposing it beyond the local machine. Never commit API keys, session files, `.env` files, or generated data.

Any key previously pasted into chat, committed, or shared should be revoked and replaced in its provider dashboard.

## CSV input

Upload a CSV containing a column whose name includes `comment`. If no matching column exists, the first column is used.