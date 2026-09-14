from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
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
USE_LOCAL_MODEL_FOR_TESTING = True
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
    "stats": {"total_imported": 0, "excluded": 0, "after_cleaning": 0, "source": ""},
    "raw_preview": [],
    "cleaned_preview": [],
}

CREDENTIAL_SERVICE = "Pul Romanized Pashto Sentiment Analyzer"
CREDENTIAL_NAMES = (
    "yt_api_key",
)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

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

def flash(request, message, category="message"):
    request.session.setdefault("flashes", []).append({"category": category, "message": message})

def pop_flashed_messages(request):
    return request.session.pop("flashes", [])

def redirect_to_index():
    return RedirectResponse(url="/", status_code=303)

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
            for _ in range(20):
                try:
                    result = await client.get(poll_url, timeout=HF_SPACE_TIMEOUT)
                    result.raise_for_status()
                    text_stream = result.text
                    if not text_stream:
                        time.sleep(1)
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
                                raise ValueError(str(output.get("error")))
                            if output is not None:
                                return parse_hf_prediction_output(output)
                except Exception:
                    pass
                time.sleep(1)

            if isinstance(last_payload, dict) and last_payload.get("output") and isinstance(last_payload.get("output"), dict):
                if last_payload["output"].get("error"):
                    raise ValueError(str(last_payload["output"].get("error")))

            raise TimeoutError("HF Space did not return a completed prediction in time.")
        except httpx.HTTPError as exc:
            raise RuntimeError(f"HF Space request failed: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"HF Space inference error: {str(exc)}") from exc


@app.post("/process/clean")
async def process_clean(request: Request):
    form = await request.form()
    file = form.get("csv_file")
    if file is None or not getattr(file, "filename", "") or not callable(getattr(file, "read", None)):
        flash(request, "Choose a CSV file first.", "error")
        return redirect_to_index()
    try:
        df = pd.read_csv(io.BytesIO(await file.read()), encoding="utf-8-sig")
        comment_col = next((col for col in df.columns if "comment" in col.lower()), df.columns[0])
        raw_comments = df[comment_col].dropna().astype(str).tolist()
        cleaned_comments = [cleaned for text in raw_comments if (cleaned := clean_comments(text))]
        if not cleaned_comments:
            flash(request, "No usable comments remained after cleaning.", "warning")
            return redirect_to_index()
        store_cleaned_stage(raw_comments, cleaned_comments, "Uploaded CSV")
        flash(request, "Step 1 complete: CSV cleaned. Download it or continue to language detection.", "success")
    except Exception as exc:
        flash(request, f"Error reading CSV: {str(exc)}", "error")
    return redirect_to_index()


@app.post("/process/detect")
async def process_detect(request: Request):
    if not latest_result["cleaned_comments"]:
        flash(request, "Clean the CSV before running language detection.", "warning")
        return redirect_to_index()
    try:
        language_rows = []
        for comment in latest_result["cleaned_comments"]:
            if USE_LOCAL_MODEL_FOR_TESTING:
                prediction, confidence = predict_pashto_with_local(comment)
            else:
                prediction, confidence = await predict_pashto_with_hf(comment)
            language_rows.append((comment, prediction))
        if USE_LOCAL_MODEL_FOR_TESTING:
            release_local_model()
        store_language_stage(language_rows)
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

@app.api_route("/", methods=["GET", "POST"])
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
                if USE_LOCAL_MODEL_FOR_TESTING:
                    prediction, confidence = predict_pashto_with_local(comment)
                else:
                    prediction, confidence = await predict_pashto_with_hf(comment)
                if prediction == "pashto":
                    pashto_comments.append(comment)
                result_rows.append([comment, prediction, "not analyzed"])

            if USE_LOCAL_MODEL_FOR_TESTING:
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