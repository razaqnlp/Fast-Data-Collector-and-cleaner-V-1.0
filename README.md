# Romanized Pashto Sentiment Analyzer

A small Flask web app that fetches YouTube comments or accepts a CSV upload, removes links and unsupported text, and uses an LLM to classify Romanized Pashto comments as Positive, Negative, or Neutral. Results can be downloaded as CSV or Excel.

## Requirements

- Python 3.10 or newer
- A YouTube Data API v3 key when using YouTube input
- At least one LLM key: Groq or Gemini for FreeFlow, or OpenAI for ChatGPT mode

## Setup

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Copy `config.example.json` to `config.json` and enter **your own** keys, or enter them through the app's Settings button. Never commit `config.json`.

4. Set a private Flask session secret for anything beyond local testing:

   ```powershell
   $env:FLASK_SECRET_KEY = "replace-with-a-long-random-value"
   ```

5. Start the app:

   ```powershell
   python app.py
   ```

6. Open http://127.0.0.1:5000 in your browser.

## API keys and security

Please use your own YouTube API key and your own LLM API key(s). The app stores keys locally in the ignored `config.json` file and does not need them in source code.

The keys previously present in this project have been removed from the files, but removal does not revoke keys that may already have been copied. The owner should revoke or rotate every previously exposed YouTube, Groq, Gemini, and OpenAI key in the corresponding provider dashboard before using this project publicly.

Do not commit `config.json`, `.env`, session files, or API keys. If a secret is ever committed, rotate it immediately and remove it from the repository history using a dedicated history-rewrite tool.

## CSV input

Upload a CSV containing a column whose name includes `comment`. If no such column exists, the first column is used.