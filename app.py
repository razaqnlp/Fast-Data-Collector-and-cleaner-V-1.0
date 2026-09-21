from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import asyncio
import googleapiclient.discovery
from googleapiclient.errors import HttpError
import re
import pandas as pd
import io
import csv
import os
import time
import json
import keyring
import gc
from datetime import datetime, timezone
from openpyxl import Workbook
import httpx

try:
    import fasttext
except ImportError:
    fasttext = None

import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

app = FastAPI(title="Romanized Pashto Sentiment Analyzer")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("FLASK_SECRET_KEY") or os.urandom(32).hex(),
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))

# API keys are stored in the operating system credential vault.
HF_SPACE_URL = "https://abdul-razaq-ork-romanized-pastho-detector.hf.space"
HF_SPACE_TIMEOUT = 30.0
LOCAL_MODEL_PATH = r"D:\data collection app\pashto_classifier.bin"
USE_LOCAL_MODEL_FOR_TESTING = os.environ.get("USE_LOCAL_FASTTEXT", "").strip().lower() in {"1", "true", "yes"}
SENTIMENT_MODEL_NAME = "abdul-razaq-ork/Romanized_Pashto_Sentiment"
HF_SENTIMENT_API_URL = f"https://router.huggingface.co/hf-inference/models/{SENTIMENT_MODEL_NAME}"
local_model = None
sentiment_tokenizer = None
sentiment_model = None
SENTIMENT_LABELS = {
    0: "positive",
    1: "negative",
    2: "neutral",
}
latest_result = {
    "stage": "empty",
    "raw_comments": [],
    "cleaned_comments": [],
    "pashto_comments": [],
    "language_csv": "",
    "cleaned_csv": "",
    "sentiment_csv": "",
    "result_csv": "",
    "pashto_sentences_csv": "",
    "pashto_sentiment_csv": "",
    "collected_filename": "",
    "collected_comments": [],
    "stats": {"total_imported": 0, "excluded": 0, "after_cleaning": 0, "source": ""},
    "import_info": {"filename": "", "columns": [], "comment_column": "", "file_size": 0},
    "raw_preview": [],
    "cleaned_preview": [],
}

CREDENTIAL_SERVICE = "Pul Romanized Pashto Sentiment Analyzer"
CREDENTIAL_NAMES = (
    "yt_api_key",
)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
COLLECTED_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "collected_data")

def load_config():
    legacy_config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            legacy_config = json.load(f)

    for name in CREDENTIAL_NAMES:
        value = legacy_config.get(name, "").strip()
        if value and not keyring.get_password(CREDENTIAL_SERVICE, name):
            keyring.set_password(CREDENTIAL_SERVICE, name, value)

    if legacy_config:
        os.remove(CONFIG_FILE)

    return {
        name: keyring.get_password(CREDENTIAL_SERVICE, name) or ""
        for name in CREDENTIAL_NAMES
    }

def save_config(config):
    for name in CREDENTIAL_NAMES:
        value = config.get(name, "").strip()
        if value:
            keyring.set_password(CREDENTIAL_SERVICE, name, value)


def save_youtube_comments(comments, video_id, custom_filename=""):
    os.makedirs(COLLECTED_DATA_DIR, exist_ok=True)
    custom_filename = re.sub(r"[^A-Za-z0-9_. -]", "", str(custom_filename or "")).strip()
    custom_filename = os.path.basename(custom_filename)
    if custom_filename:
        if not custom_filename.lower().endswith(".csv"):
            custom_filename += ".csv"
        filename = custom_filename
        stem, extension = os.path.splitext(filename)
        suffix = 2
        while os.path.exists(os.path.join(COLLECTED_DATA_DIR, filename)):
            filename = f"{stem}_{suffix}{extension}"
            suffix += 1
    else:
        existing_numbers = []
        for filename in os.listdir(COLLECTED_DATA_DIR):
            match = re.fullmatch(r"youtube_comments_(\d+)\.csv", filename)
            if match:
                existing_numbers.append(int(match.group(1)))
        next_number = max(existing_numbers, default=0) + 1
        filename = f"youtube_comments_{next_number:03d}.csv"
    filepath = os.path.join(COLLECTED_DATA_DIR, filename)
    collection_date = datetime.now(timezone.utc).isoformat()

    with open(filepath, "w", newline="", encoding="utf-8-sig") as output:
        output.write("sep=,\n")
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "video_id", "original_text", "collection_date"],
        )
        writer.writeheader()
        writer.writerows(
            {
                "id": row_id,
                "video_id": video_id,
                "original_text": comment,
                "collection_date": collection_date,
            }
            for row_id, comment in enumerate(comments, start=1)
        )
    return filename


def youtube_video_was_collected(video_id):
    normalized_video_id = str(video_id).strip()
    if not normalized_video_id or not os.path.isdir(COLLECTED_DATA_DIR):
        return None
    for filename in os.listdir(COLLECTED_DATA_DIR):
        if not filename.lower().endswith(".csv"):
            continue
        try:
            with open(os.path.join(COLLECTED_DATA_DIR, filename), newline="", encoding="utf-8-sig") as source:
                first_line = source.readline()
                if not first_line.lower().startswith("sep=,"):
                    source.seek(0)
                for row in csv.DictReader(source):
                    if str(row.get("video_id", "")).strip() == normalized_video_id:
                        return filename
        except (OSError, csv.Error):
            continue
    return None


def read_comment_csv(file_bytes):
    csv_start = file_bytes.lstrip(b"\xef\xbb\xbf \t\r\n")
    skiprows = 1 if csv_start.startswith(b"sep=,") else 0
    return pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8-sig", skiprows=skiprows)

def flash(request, message, category="message", **details):
    request.session.setdefault("flashes", []).append({"category": category, "message": message, **details})

def pop_flashed_messages(request):
    return request.session.pop("flashes", [])

def redirect_to_index():
    return RedirectResponse(url="/", status_code=303)

def clean_comments(
    text,
    remove_links=True,
    remove_emojis=True,
    remove_mentions_tags=True,
    normalize_whitespace=True,
    remove_short=False,
):
    if not isinstance(text, str):
        return ""
    if remove_links:
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
    if remove_emojis:
        text = emoji_pattern.sub(r'', text)
    text = re.sub(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+', '', text)
    if remove_emojis:
        allowed = r"[^A-Za-z0-9.,!?\'\"\s@#/:_-]" if not remove_mentions_tags else r"[^A-Za-z0-9.,!?\'\"\s/:_-]"
        text = re.sub(allowed, '', text)
    if remove_mentions_tags:
        text = re.sub(r'(?<!\S)[@#][A-Za-z0-9_]+', '', text)
    if normalize_whitespace:
        text = re.sub(r'\s+', ' ', text).strip()
    else:
        text = text.strip()
    if remove_short and len(text.split()) < 3:
        return ""
    return text


def normalize_hf_prediction_label(label):
    if label is None:
        return "not_pashto"
    cleaned = str(label).strip().lower()
    if cleaned == "pashto":
        return "pashto"
    if cleaned == "not_pashto":
        return "not_pashto"
    if cleaned == "not pashto":
        return "not_pashto"
    return cleaned


def parse_hf_prediction_output(payload):
    if not isinstance(payload, (list, tuple)) or len(payload) != 2:
        if isinstance(payload, dict) and payload.get("error"):
            raise ValueError(str(payload.get("error")))
        raise ValueError("Unexpected Hugging Face inference response format.")

    prediction = normalize_hf_prediction_label(payload[0])
    confidence = float(payload[1])
    return prediction, confidence


def fallback_pashto_prediction(text: str):
    if not isinstance(text, str):
        return "not_pashto"
    cleaned = re.sub(r'\s+', ' ', text.strip())
    if not cleaned:
        return "not_pashto"

    pashto_chars = sum(1 for ch in cleaned if '\u0600' <= ch <= '\u06FF' or '\u0750' <= ch <= '\u077F' or '\u08A0' <= ch <= '\u08FF')
    latin_letters = sum(1 for ch in cleaned if ch.isalpha() and ch.isascii())
    if pashto_chars >= 2 or (latin_letters and len(cleaned.split()) <= 4 and any(ch in cleaned.lower() for ch in "aiouae")):
        return "pashto"
    return "not_pashto"


def format_fasttext_csv(rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue().rstrip("\r\n")


def normalize_local_prediction_label(label):
    cleaned = str(label or "").strip().lower()
    if cleaned.startswith("__label__"):
        cleaned = cleaned[len("__label__"):]
    return "pashto" if cleaned == "pashto" else "not_pashto"


def predict_pashto_with_local(text: str):
    global local_model

    if fasttext is None:
        raise RuntimeError("The fasttext package is not installed.")
    if not os.path.exists(LOCAL_MODEL_PATH):
        raise RuntimeError(f"Local model not found: {LOCAL_MODEL_PATH}")
    if local_model is None:
        local_model = fasttext.load_model(LOCAL_MODEL_PATH)

    labels, probabilities = local_model.predict(text.strip(), k=1)
    if not labels or not probabilities:
        return "not_pashto", 0.0
    return normalize_local_prediction_label(labels[0]), float(probabilities[0])


def local_fasttext_available():
    return USE_LOCAL_MODEL_FOR_TESTING and fasttext is not None and os.path.exists(LOCAL_MODEL_PATH)


def release_local_model():
    global local_model
    local_model = None
    gc.collect()


def predict_sentiment(text: str):
    return predict_sentiments([text])[0]


def predict_sentiments(texts):
    global sentiment_tokenizer, sentiment_model

    if sentiment_tokenizer is None or sentiment_model is None:
        sentiment_tokenizer = AutoTokenizer.from_pretrained(SENTIMENT_MODEL_NAME)
        sentiment_model = AutoModelForSequenceClassification.from_pretrained(SENTIMENT_MODEL_NAME)
        sentiment_model.eval()

    inputs = sentiment_tokenizer(
        texts,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=64,
    )
    with torch.no_grad():
        output = sentiment_model(**inputs)

    probabilities = torch.softmax(output.logits, dim=1)
    predictions = []
    for row in probabilities:
        class_id = torch.argmax(row).item()
        predictions.append((SENTIMENT_LABELS[class_id], float(row[class_id])))
    return predictions


async def predict_sentiments_with_hf_api(texts):
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN is not configured. Set a Hugging Face access token before assigning sentiment.")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            HF_SENTIMENT_API_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={"inputs": texts, "parameters": {"return_all_scores": True}},
        )
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", response.text)
            except ValueError:
                detail = response.text
            raise RuntimeError(f"Hugging Face sentiment API error ({response.status_code}): {detail}")

        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"Hugging Face sentiment API error: {payload['error']}")

    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        payload = [payload]
    predictions = []
    for scores in payload:
        if not isinstance(scores, list):
            raise RuntimeError("Unexpected Hugging Face sentiment API response format.")
        normalized = []
        for score in scores:
            label = str(score.get("label", "")).strip().lower()
            if label in {"label_0", "0", "positive"}:
                label = "positive"
            elif label in {"label_1", "1", "negative"}:
                label = "negative"
            elif label in {"label_2", "2", "neutral"}:
                label = "neutral"
            normalized.append((label, float(score.get("score", 0.0))))
        predictions.append(max(normalized, key=lambda item: item[1]))
    return predictions


def store_cleaned_stage(raw_comments, cleaned_comments, source):
    global latest_result
    latest_result = {
        **latest_result,
        "stage": "cleaned",
        "raw_comments": raw_comments,
        "cleaned_comments": cleaned_comments,
        "pashto_comments": [],
        "language_csv": "",
        "cleaned_csv": format_fasttext_csv([(comment,) for comment in cleaned_comments]),
        "sentiment_csv": "",
        "result_csv": "",
        "pashto_sentences_csv": "",
        "pashto_sentiment_csv": "",
        "stats": {
            "total_imported": len(raw_comments),
            "excluded": len(raw_comments) - len(cleaned_comments),
            "after_cleaning": len(cleaned_comments),
            "source": source,
        },
        "raw_preview": raw_comments[:20],
        "cleaned_preview": cleaned_comments[:20],
    }


def store_language_stage(language_rows):
    global latest_result
    pashto_comments = [row[0] for row in language_rows if row[1] == "pashto"]
    language_csv = format_fasttext_csv(language_rows)
    latest_result.update({
        "stage": "detected",
        "pashto_comments": pashto_comments,
        "language_csv": language_csv,
        "cleaned_csv": latest_result["cleaned_csv"],
        "sentiment_csv": "",
        "result_csv": language_csv,
        "pashto_sentences_csv": "\n".join(pashto_comments),
        "pashto_sentiment_csv": "",
    })


def store_sentiment_stage(sentiment_rows):
    global latest_result
    sentiment_csv = format_fasttext_csv(sentiment_rows)
    latest_result.update({
        "stage": "sentiment",
        "sentiment_csv": sentiment_csv,
        "result_csv": sentiment_csv,
        "pashto_sentiment_csv": sentiment_csv,
    })


async def predict_pashto_with_hf(text: str):
    if not isinstance(text, str):
        raise ValueError("Prediction input must be a string.")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Empty input for hosted HF model.")

    async with httpx.AsyncClient(timeout=httpx.Timeout(HF_SPACE_TIMEOUT, connect=HF_SPACE_TIMEOUT)) as client:
        try:
            session_hash = os.urandom(8).hex()
            join = await client.post(
                f"{HF_SPACE_URL}/gradio_api/queue/join",
                json={"data": [cleaned], "fn_index": 2, "trigger_id": 13, "session_hash": session_hash},
                headers={"Content-Type": "application/json"},
            )
            join.raise_for_status()
            event_id = join.json().get("event_id")
            if not event_id:
                raise ValueError("HF Space did not return an event_id.")

            poll_url = f"{HF_SPACE_URL}/gradio_api/queue/data?session_hash={session_hash}"
            last_payload = None
            for _ in range(8):
                try:
                    result = await client.get(poll_url, timeout=HF_SPACE_TIMEOUT)
                    result.raise_for_status()
                    text_stream = result.text
                    if not text_stream:
                        await asyncio.sleep(0.5)
                        continue
                    for line in text_stream.splitlines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        last_payload = payload
                        if payload.get("msg") == "process_completed":
                            output = payload.get("output")
                            if isinstance(output, dict) and output.get("error"):
                                error_text = str(output.get("error"))
                                if "ZeroGPU" in error_text or "quota" in error_text.lower():
                                    return fallback_pashto_prediction(cleaned), 0.55
                                raise ValueError(error_text)
                            if output is not None:
                                return parse_hf_prediction_output(output)
                except Exception:
                    pass
                await asyncio.sleep(0.5)

            if isinstance(last_payload, dict) and last_payload.get("output") and isinstance(last_payload.get("output"), dict):
                output = last_payload["output"]
                if output.get("error"):
                    error_text = str(output.get("error"))
                    if "ZeroGPU" in error_text or "quota" in error_text.lower():
                        return fallback_pashto_prediction(cleaned), 0.55
                    raise ValueError(error_text)

            return fallback_pashto_prediction(cleaned), 0.55
        except httpx.HTTPError as exc:
            return fallback_pashto_prediction(cleaned), 0.55
        except Exception as exc:
            return fallback_pashto_prediction(cleaned), 0.55


@app.post("/import/csv")
async def import_csv(request: Request):
    form = await request.form()
    file = form.get("csv_file")
    if file is None or not getattr(file, "filename", "") or not callable(getattr(file, "read", None)):
        flash(request, "Choose a CSV file first.", "error")
        return redirect_to_index()
    try:
        file_bytes = await file.read()
        df = read_comment_csv(file_bytes)
        comment_col = next((col for col in df.columns if "comment" in col.lower()), df.columns[0])
        raw_comments = df[comment_col].dropna().astype(str).tolist()
        latest_result.update({
            "stage": "empty",
            "raw_comments": raw_comments,
            "cleaned_comments": [],
            "pashto_comments": [],
            "language_csv": "",
            "cleaned_csv": "",
            "sentiment_csv": "",
            "result_csv": "",
            "pashto_sentences_csv": "",
            "pashto_sentiment_csv": "",
            "raw_preview": raw_comments[:20],
            "cleaned_preview": [],
            "stats": {"total_imported": len(raw_comments), "excluded": 0, "after_cleaning": 0, "source": "Uploaded CSV"},
        })
        latest_result["import_info"] = {
            "filename": getattr(file, "filename", ""),
            "columns": [str(column) for column in df.columns],
            "comment_column": str(comment_col),
            "file_size": len(file_bytes),
        }
        flash(request, f"Imported {len(raw_comments)} comments. Choose your cleaning rules and run cleaning.", "success")
    except Exception as exc:
        flash(request, f"Error reading CSV: {str(exc)}", "error")
    return redirect_to_index()


@app.post("/process/clean")
async def process_clean(request: Request):
    form = await request.form()
    file = form.get("csv_file")
    try:
        if file is not None and getattr(file, "filename", "") and callable(getattr(file, "read", None)):
            file_bytes = await file.read()
            df = read_comment_csv(file_bytes)
            comment_col = next((col for col in df.columns if "comment" in col.lower()), df.columns[0])
            raw_comments = df[comment_col].dropna().astype(str).tolist()
            latest_result["raw_comments"] = raw_comments
            latest_result["import_info"] = {
                "filename": getattr(file, "filename", ""),
                "columns": [str(column) for column in df.columns],
                "comment_column": str(comment_col),
                "file_size": len(file_bytes),
            }
        else:
            raw_comments = latest_result["raw_comments"]
        if not raw_comments:
            flash(request, "Import a CSV from the Collect Data tab first.", "error")
            return redirect_to_index()
        options = {
            "remove_links": "remove_links" in form,
            "remove_emojis": "remove_emojis" in form,
            "remove_mentions_tags": "remove_mentions_tags" in form,
            "normalize_whitespace": "normalize_whitespace" in form,
            "remove_short": "remove_short" in form,
        }
        cleaned_comments = []
        seen = set()
        for text in raw_comments:
            cleaned = clean_comments(text, **options)
            if not cleaned:
                continue
            if "remove_duplicates" in form:
                normalized = cleaned.casefold()
                if normalized in seen:
                    continue
                seen.add(normalized)
            cleaned_comments.append(cleaned)
        if not cleaned_comments:
            flash(request, "No usable comments remained after cleaning.", "warning")
            return redirect_to_index()
        store_cleaned_stage(raw_comments, cleaned_comments, "Uploaded CSV")
        flash(request, "Step 1 complete: CSV cleaned. Download it or continue to language detection.", "success")
    except Exception as exc:
        flash(request, f"Error reading CSV: {str(exc)}", "error")
    return redirect_to_index()


@app.post("/collect/youtube")
async def collect_youtube(request: Request):
    form = await request.form()
    video_id = str(form.get("video_id", "")).strip()
    force_rescrape = str(form.get("force_rescrape", "")).lower() == "1"
    edit_filename = str(form.get("edit_filename", "")).lower() == "1"
    custom_filename = str(form.get("custom_filename", "")).strip() if edit_filename else ""
    config = load_config()
    yt_api_key = config.get("yt_api_key", "").strip()

    if not video_id:
        flash(request, "Enter a YouTube video ID before collecting comments.", "error")
        return RedirectResponse(url="/?view=collector", status_code=303)
    if not yt_api_key:
        flash(request, "Save a YouTube API key in the API panel before collecting.", "error")
        return RedirectResponse(url="/?view=collector", status_code=303)

    existing_filename = youtube_video_was_collected(video_id)
    if existing_filename and not force_rescrape:
        flash(
            request,
            f"This video was already collected in {existing_filename}.",
            "duplicate",
            video_id=video_id,
            custom_filename=custom_filename,
            edit_filename=edit_filename,
        )
        return RedirectResponse(url="/?view=collector", status_code=303)

    raw_comments = []
    try:
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=yt_api_key)
        youtube.videos().list(part="id", id=video_id).execute()
        next_page_token = None

        while True:
            response = youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=100,
                pageToken=next_page_token,
                textFormat="plainText",
            ).execute()
            for item in response.get("items", []):
                raw_comments.append(item["snippet"]["topLevelComment"]["snippet"]["textDisplay"])

            next_page_token = response.get("nextPageToken")
            if not next_page_token or len(raw_comments) >= 15000:
                break
            time.sleep(0.35)

        if not raw_comments:
            flash(request, "No comments were found for that video.", "warning")
        else:
            collected = raw_comments[:15000]
            filename = save_youtube_comments(collected, video_id, custom_filename)
            latest_result.update({
                "collected_filename": filename,
                "collected_comments": collected,
            })
            flash(request, f"Collected {len(collected)} comments and saved {filename} on this computer.", "success")
            return RedirectResponse(url="/?view=collector&collected=1", status_code=303)
    except HttpError as exc:
        error_msg = str(exc)
        if "quota" in error_msg.lower():
            message = "YouTube API quota exceeded. Check Google Cloud Console or wait for reset."
        elif "invalid" in error_msg.lower() or "expired" in error_msg.lower():
            message = "The YouTube API key is invalid or expired. Update it in the API panel."
        else:
            message = f"YouTube API error: {error_msg}"
        flash(request, message, "error")
    except Exception as exc:
        flash(request, f"YouTube collection failed: {str(exc)}", "error")
    return RedirectResponse(url="/?view=collector", status_code=303)


@app.post("/process/detect")
async def process_detect(request: Request):
    if not latest_result["cleaned_comments"]:
        flash(request, "Clean the CSV before running language detection.", "warning")
        return redirect_to_index()
    try:
        comments = latest_result["cleaned_comments"]
        semaphore = asyncio.Semaphore(12)

        async def detect_one(comment):
            async with semaphore:
                try:
                    if local_fasttext_available():
                        prediction, confidence = predict_pashto_with_local(comment)
                    else:
                        prediction, confidence = await asyncio.wait_for(
                            predict_pashto_with_hf(comment),
                            timeout=HF_SPACE_TIMEOUT,
                        )
                    return comment, prediction, None
                except Exception as exc:
                    return comment, "not_pashto", str(exc)

        detected = await asyncio.gather(*(detect_one(comment) for comment in comments))
        language_rows = [(comment, prediction) for comment, prediction, error in detected]
        failed_count = sum(1 for comment, prediction, error in detected if error)
        if local_fasttext_available():
            release_local_model()
        store_language_stage(language_rows)
        if failed_count:
            flash(request, f"Detection completed with {failed_count} unavailable predictions marked as not Pashto.", "warning")
        else:
            flash(request, "Step 2 complete: Romanized Pashto sentences selected.", "success")
    except Exception as exc:
        flash(request, f"Language detection error: {str(exc)}", "error")
    return redirect_to_index()


@app.post("/process/sentiment")
async def process_sentiment(request: Request):
    if not latest_result["pashto_comments"]:
        flash(request, "Run language detection before assigning sentiment.", "warning")
        return redirect_to_index()
    try:
        sentiment_rows = []
        comments = latest_result["pashto_comments"]
        for offset in range(0, len(comments), 32):
            batch = comments[offset:offset + 32]
            predictions = await predict_sentiments_with_hf_api(batch)
            sentiment_rows.extend((comment, prediction[0]) for comment, prediction in zip(batch, predictions))
        store_sentiment_stage(sentiment_rows)
        flash(request, "Step 3 complete: sentiment assigned as positive, negative, or neutral.", "success")
    except Exception as exc:
        flash(request, f"Sentiment analysis error: {str(exc)}", "error")
    return redirect_to_index()

@app.get("/")
async def index(request: Request):
    global latest_result
    config = load_config()
    result_csv = latest_result["result_csv"]
    stats = latest_result["stats"]
    raw_preview = latest_result["raw_preview"]
    cleaned_preview = latest_result["cleaned_preview"]

    if request.method == "POST":
        form = await request.form()
        mode = form.get("mode", "youtube")

        # Load config values for the local data pipeline
        yt_api_key = config.get("yt_api_key", "").strip()

        raw_comments = []
        cleaned_comments = []

        # ── Mode: Upload CSV ─────────────────────────────────────────────────────
        if mode == "upload":
            file = form.get("csv_file")
            if file is None or not getattr(file, "filename", "") or not callable(getattr(file, "read", None)):
                flash(request, "No file uploaded.", "error")
                return redirect_to_index()

            try:
                df = pd.read_csv(io.BytesIO(await file.read()), encoding="utf-8-sig")
                comment_col = next((col for col in df.columns if "comment" in col.lower()), df.columns[0])
                raw_comments = df[comment_col].dropna().astype(str).tolist()
                stats["source"] = "Uploaded CSV"
            except Exception as e:
                flash(request, f"Error reading CSV: {str(e)}", "error")
                return redirect_to_index()

        # ── Mode: YouTube fetch ──────────────────────────────────────────────────
        else:
            video_id = str(form.get("video_id", "")).strip()
            if not video_id:
                flash(request, "Please enter Video ID.", "error")
                return redirect_to_index()
            if not yt_api_key:
                flash(request, "YouTube API key required (set in Settings).", "error")
                return redirect_to_index()

            try:
                youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=yt_api_key)
                youtube.videos().list(part="id", id=video_id).execute()
            except HttpError as e:
                error_msg = str(e)
                if "quota" in error_msg.lower():
                    flash(request, "YouTube API quota exceeded or limit reached. Wait for reset or check Google Cloud Console.", "error")
                elif "invalid" in error_msg.lower() or "expired" in error_msg.lower():
                    flash(request, "YouTube API key invalid or expired. Please update in Settings.", "error")
                else:
                    flash(request, f"YouTube API error: {error_msg}", "error")
                return redirect_to_index()
            except Exception as e:
                flash(request, f"Connection failed: {str(e)}", "error")
                return redirect_to_index()

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
                        flash(request, "Safety limit reached (~15k comments).", "warning")
                        break

                except HttpError as e:
                    error_msg = str(e)
                    if "quota" in error_msg.lower():
                        flash(request, "YouTube API quota exceeded during fetch. Wait for reset.", "error")
                    else:
                        flash(request, f"Fetch error: {error_msg}", "error")
                    return redirect_to_index()
                except Exception as e:
                    flash(request, f"Unexpected error: {str(e)}", "error")
                    return redirect_to_index()

        # ── Cleaning ─────────────────────────────────────────────────────────────
        for c in raw_comments:
            cleaned = clean_comments(c)
            if cleaned:
                cleaned_comments.append(cleaned)

        stats["total_imported"] = len(raw_comments)
        stats["after_cleaning"] = len(cleaned_comments)
        stats["excluded"] = stats["total_imported"] - stats["after_cleaning"]

        if not cleaned_comments:
            flash(request, "No usable Romanized comments after cleaning.", "warning")
            return redirect_to_index()


        try:
            pashto_comments = []
            result_rows = []
            for comment in cleaned_comments:
                if local_fasttext_available():
                    prediction, confidence = predict_pashto_with_local(comment)
                else:
                    prediction, confidence = await predict_pashto_with_hf(comment)
                if prediction == "pashto":
                    pashto_comments.append(comment)
                result_rows.append([comment, prediction, "not analyzed"])

            if local_fasttext_available():
                release_local_model()

            pashto_rows = [row for row in result_rows if row[1] == "pashto"]
            for offset in range(0, len(pashto_rows), 32):
                batch_rows = pashto_rows[offset:offset + 32]
                predictions = predict_sentiments([row[0] for row in batch_rows])
                for row, prediction in zip(batch_rows, predictions):
                    row[2] = prediction[0]

            if not pashto_comments:
                flash(request, "The model returned no pashto rows. Showing all classified rows below.", "warning")
            else:
                flash(request, f"{len(pashto_comments)} pashto rows retained. Showing all classified rows below.", "success")

            result_csv = format_fasttext_csv(result_rows)
            pashto_sentences_csv = "\n".join(pashto_comments)
            pashto_sentiment_csv = format_fasttext_csv(
                [(row[0], row[2]) for row in result_rows if row[1] == "pashto"]
            )
        except Exception as exc:
            flash(request, f"Hosted HF model error: {str(exc)}", "error")
            return redirect_to_index()

        # Previews (first 20)
        raw_preview = raw_comments[:20]
        cleaned_preview = cleaned_comments[:20]

        latest_result = {
            "result_csv": result_csv,
            "pashto_sentences_csv": pashto_sentences_csv,
            "pashto_sentiment_csv": pashto_sentiment_csv,
            "stats": stats,
            "raw_preview": raw_preview,
            "cleaned_preview": cleaned_preview,
        }

        flash(request, "Processing complete! Scroll down to see data.", "success")

        return redirect_to_index()

    messages = pop_flashed_messages(request)
    config_status = {name: bool(value) for name, value in config.items()}
    show_collector = request.query_params.get("view") == "collector"
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "stage": latest_result["stage"],
            "pashto_preview": latest_result["pashto_comments"][:20],
            "result_csv": result_csv,
            "language_csv": latest_result["language_csv"],
            "cleaned_csv": latest_result["cleaned_csv"],
            "sentiment_csv": latest_result["sentiment_csv"],
            "stats": stats,
            "raw_preview": raw_preview,
            "cleaned_preview": cleaned_preview,
            "config": config_status,
            "messages": messages,
            "show_collector": show_collector,
            "collected_filename": latest_result["collected_filename"],
            "collected_comments": latest_result["collected_comments"],
            "import_info": latest_result["import_info"],
        },
    )

@app.post("/save_settings")
async def save_settings(request: Request):
    form = await request.form()
    updated_config = {
        "yt_api_key": str(form.get("yt_api_key", "")).strip(),
    }
    save_config(updated_config)
    flash(request, "API settings saved successfully!", "success")
    return redirect_to_index()

@app.get("/export/{filetype}")
def export(request: Request, filetype: str):
    staged_exports = {
        "cleaned": (latest_result["cleaned_csv"], "cleaned_comments.csv"),
        "language": (latest_result["language_csv"], "pashto_language_selection.csv"),
        "sentiment": (latest_result["sentiment_csv"], "pashto_sentiment_results.csv"),
    }
    if filetype in staged_exports:
        export_csv, filename = staged_exports[filetype]
        if not export_csv:
            flash(request, "Complete the previous processing step first.", "warning")
            return redirect_to_index()
        return StreamingResponse(
            iter([export_csv.encode("utf-8-sig")]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    if filetype == "collected" and latest_result["collected_filename"]:
        filepath = os.path.join(COLLECTED_DATA_DIR, latest_result["collected_filename"])
        if os.path.exists(filepath):
            with open(filepath, "rb") as collected_file:
                return StreamingResponse(
                    iter([collected_file.read()]),
                    media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{latest_result["collected_filename"]}"'},
                )
        flash(request, "The collected file is no longer available on this computer.", "warning")
        return redirect_to_index()

    result_csv = latest_result["result_csv"]
    if not result_csv:
        flash(request, "No sentiment data to export.", "error")
        return redirect_to_index()

    if filetype == "csv":
        return StreamingResponse(
            iter([result_csv.encode("utf-8-sig")]),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="sentiment_analysis.csv"'}
        )

    if filetype in {"pashto_sentences", "pashto_sentiment"}:
        export_csv = latest_result[
            "pashto_sentences_csv" if filetype == "pashto_sentences" else "pashto_sentiment_csv"
        ]
        filename = (
            "pashto_sentences.csv"
            if filetype == "pashto_sentences"
            else "pashto_sentences_with_sentiment.csv"
        )
        if not export_csv:
            flash(request, "No Pashto sentences were found to export.", "warning")
            return redirect_to_index()
        return StreamingResponse(
            iter([export_csv.encode("utf-8-sig")]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    elif filetype == "excel":
        df = pd.read_csv(io.StringIO(result_csv), header=None)
        if len(df.columns) == 3:
            df.columns = ["sentence", "language_label", "sentiment"]
        else:
            df.columns = ["sentence", "sentiment"]
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_buffer.seek(0)
        return StreamingResponse(
            excel_buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": 'attachment; filename="sentiment_analysis.xlsx"'}
        )

    flash(request, "Invalid export type.", "error")
    return redirect_to_index()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=os.environ.get("FLASK_DEBUG") == "1")