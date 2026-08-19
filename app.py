from flask import Flask, render_template, request, flash, session, send_file, redirect, url_for
import googleapiclient.discovery
from googleapiclient.errors import HttpError
import re
from freeflow_llm import FreeFlowClient
import pandas as pd
import io
import os
import time
import json
from openpyxl import Workbook
from flask_session import Session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "local-development-secret-change-me")
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

# Config file for persistent API keys
CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def clean_comments(text):
    if not isinstance(text, str):
        return ""
    text = re.sub(r'http\S+|www\.\S+', '', text)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002700-\U000027BF"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE)
    text = emoji_pattern.sub(r'', text)
    text = re.sub(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+', '', text)
    text = re.sub(r'[^A-Za-z0-9.,!?\'"\s-]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

@app.route("/", methods=["GET", "POST"])
def index():
    config = load_config()
    result_csv = session.get('result_csv', '')
    stats = session.get('stats', {"total_imported": 0, "excluded": 0, "after_cleaning": 0, "source": ""})
    raw_preview = session.get('raw_preview', [])
    cleaned_preview = session.get('cleaned_preview', [])

    if request.method == "POST":
        mode = request.form.get("mode", "youtube")

        # Load API keys from config (since settings submit separately)
        yt_api_key = config.get("yt_api_key", "").strip()
        groq_keys = [k for k in [config.get("groq_key1", ""), config.get("groq_key2", "")] if k.strip()]
        gemini_keys = [k for k in [config.get("gemini_key1", ""), config.get("gemini_key2", "")] if k.strip()]
        chatgpt_key = config.get("chatgpt_api_key", "").strip()

        # Set env for FreeFlow
        if groq_keys:
            os.environ["GROQ_API_KEY"] = json.dumps(groq_keys)
        if gemini_keys:
            os.environ["GEMINI_API_KEY"] = json.dumps(gemini_keys)

        raw_comments = []
        cleaned_comments = []

        # ── Mode: Upload CSV ─────────────────────────────────────────────────────
        if mode == "upload":
            if "csv_file" not in request.files:
                flash("No file uploaded.", "error")
                return redirect(url_for("index"))

            file = request.files["csv_file"]
            if file.filename == "":
                flash("No file selected.", "error")
                return redirect(url_for("index"))

            try:
                df = pd.read_csv(file, encoding="utf-8-sig")
                comment_col = next((col for col in df.columns if "comment" in col.lower()), df.columns[0])
                raw_comments = df[comment_col].dropna().astype(str).tolist()
                stats["source"] = "Uploaded CSV"
            except Exception as e:
                flash(f"Error reading CSV: {str(e)}", "error")
                return redirect(url_for("index"))

        # ── Mode: YouTube fetch ──────────────────────────────────────────────────
        else:
            video_id = request.form.get("video_id", "").strip()
            if not video_id:
                flash("Please enter Video ID.", "error")
                return redirect(url_for("index"))
            if not yt_api_key:
                flash("YouTube API key required (set in Settings).", "error")
                return redirect(url_for("index"))

            try:
                youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=yt_api_key)
                youtube.videos().list(part="id", id=video_id).execute()
            except HttpError as e:
                error_msg = str(e)
                if "quota" in error_msg.lower():
                    flash("YouTube API quota exceeded or limit reached. Wait for reset or check Google Cloud Console.", "error")
                elif "invalid" in error_msg.lower() or "expired" in error_msg.lower():
                    flash("YouTube API key invalid or expired. Please update in Settings.", "error")
                else:
                    flash(f"YouTube API error: {error_msg}", "error")
                return redirect(url_for("index"))
            except Exception as e:
                flash(f"Connection failed: {str(e)}", "error")
                return redirect(url_for("index"))

            next_page_token = None
            stats["source"] = "YouTube"

            while True:
                try:
                    req = youtube.commentThreads().list(
                        part="snippet",
                        videoId=video_id,
                        maxResults=100,
                        pageToken=next_page_token,
                        textFormat="plainText"
                    )
                    res = req.execute()

                    for item in res.get("items", []):
                        comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
                        raw_comments.append(comment)

                    next_page_token = res.get("nextPageToken")
                    if not next_page_token:
                        break

                    time.sleep(0.35)

                    if len(raw_comments) > 15000:
                        flash("Safety limit reached (~15k comments).", "warning")
                        break

                except HttpError as e:
                    error_msg = str(e)
                    if "quota" in error_msg.lower():
                        flash("YouTube API quota exceeded during fetch. Wait for reset.", "error")
                    else:
                        flash(f"Fetch error: {error_msg}", "error")
                    return redirect(url_for("index"))
                except Exception as e:
                    flash(f"Unexpected error: {str(e)}", "error")
                    return redirect(url_for("index"))

        # ── Cleaning ─────────────────────────────────────────────────────────────
        for c in raw_comments:
            cleaned = clean_comments(c)
            if cleaned:
                cleaned_comments.append(cleaned)

        stats["total_imported"] = len(raw_comments)
        stats["after_cleaning"] = len(cleaned_comments)
        stats["excluded"] = stats["total_imported"] - stats["after_cleaning"]

        if not cleaned_comments:
            flash("No usable Romanized comments after cleaning.", "warning")
            return redirect(url_for("index"))


        # LLM choice (from UI)
        llm_choice = request.form.get("llm_choice", "freeflow")

        user_input = "\n".join(cleaned_comments)
        system_instruction = """
You are an AI that ONLY recognizes Romanized Pashto sentences.
For each sentence, provide its sentiment (Positive, Negative, Neutral) in CSV format.
The output must be strictly in CSV format with two columns:
Column 1: Romanized Pashto sentence
Column 2: Sentiment

Example:
Za khushala yum chi staso sara galay kawum,Positive
Zama tabyat theek na de,Negative

Strictly ignore english and also strictly please double check. Do NOT include any non-Romanized-Pashto sentences .
If a sentence is in another language, ignore it completely and do NOT put it in the output.
Do NOT include any explanations, headers, or extra text. Only output the valid CSV lines.

triple check the final sentiment for each sentence and make sure to only include Romanized Pashto sentences in the output.
"""

        # If user selected ChatGPT, try OpenAI first (with fallback to FreeFlow)
        result_csv = None
        llm_error = None

        if llm_choice == "chatgpt":
            if not chatgpt_key:
                flash("ChatGPT selected but no ChatGPT API key found in Settings.", "error")
                return redirect(url_for("index"))
            try:
                try:
                    import openai
                except Exception:
                    flash("openai package not installed. Run: pip install openai", "error")
                    return redirect(url_for("index"))
                openai.api_key = chatgpt_key
                messages = [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_input},
                ]
                # Use a powerful ChatGPT model; adjust if not available on account
                resp = openai.ChatCompletion.create(model="gpt-4", messages=messages, temperature=0)
                result_csv = resp.choices[0].message.content.strip()
            except Exception as e:
                llm_error = str(e)
                # continue to fallback to FreeFlow below

        # If not using ChatGPT or ChatGPT failed, use FreeFlow (Gemini prioritized, then GROQ)
        if not result_csv:
            if not gemini_keys and not groq_keys:
                flash("No valid LLM API keys provided for FreeFlow. Set at least one Gemini or Groq key in Settings.", "error")
                return redirect(url_for("index"))

            from freeflow_llm import GeminiProvider, GroqProvider
            try:
                providers = []
                if gemini_keys:
                    providers.append(GeminiProvider(api_key=gemini_keys))
                if groq_keys:
                    providers.append(GroqProvider(api_key=groq_keys))
                with FreeFlowClient(providers=providers) as client:
                    messages = [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_input}
                    ]
                    response = client.chat(messages=messages)
                result_csv = response.content.strip()
            except Exception as e:
                llm_error = str(e)

        if not result_csv or len(result_csv.splitlines()) < 1:
            if llm_error:
                flash(f"LLM error: {llm_error}", "error")
            else:
                flash("No valid result from LLMs (Gemini/Groq).", "warning")
            return redirect(url_for("index"))

        # Store in session for previews and export
        session['raw_comments'] = raw_comments
        session['cleaned_comments'] = cleaned_comments
        session['result_csv'] = result_csv
        session['stats'] = stats

        # Previews (first 20)
        raw_preview = raw_comments[:20]
        cleaned_preview = cleaned_comments[:20]

        session['raw_preview'] = raw_preview
        session['cleaned_preview'] = cleaned_preview

        flash("Processing complete! Scroll down to see data.", "success")

        return redirect(url_for("index"))

    return render_template("index.html", result_csv=result_csv, stats=stats, raw_preview=raw_preview, cleaned_preview=cleaned_preview, config=config)

@app.route("/save_settings", methods=["POST"])
def save_settings():
    updated_config = {
        "yt_api_key": request.form.get("yt_api_key", "").strip(),
        "groq_key1": request.form.get("groq_key1", "").strip(),
        "groq_key2": request.form.get("groq_key2", "").strip(),
        "gemini_key1": request.form.get("gemini_key1", "").strip(),
        "gemini_key2": request.form.get("gemini_key2", "").strip(),
        "chatgpt_api_key": request.form.get("chatgpt_api_key", "").strip()
    }
    save_config(updated_config)
    flash("API settings saved successfully!", "success")
    return redirect(url_for("index"))

@app.route("/export/<filetype>")
def export(filetype):
    result_csv = session.get('result_csv', '')
    if not result_csv:
        flash("No sentiment data to export.", "error")
        return redirect(url_for("index"))

    if filetype == "csv":
        csv_buffer = io.StringIO(result_csv)
        return send_file(
            io.BytesIO(csv_buffer.getvalue().encode("utf-8-sig")),
            mimetype="text/csv",
            as_attachment=True,
            download_name="sentiment_analysis.csv"
        )

    elif filetype == "excel":
        df = pd.read_csv(io.StringIO(result_csv), header=None, names=["sentence", "sentiment"])
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_buffer.seek(0)
        return send_file(
            excel_buffer,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="sentiment_analysis.xlsx"
        )

    flash("Invalid export type.", "error")
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)