from datetime import datetime
from flask import Flask, flash, render_template, request, redirect, url_for, send_file
from google.cloud import texttospeech, storage, language_v1
import vertexai
from vertexai.generative_models import GenerativeModel, Part
import os

# Set up Google Cloud Storage bucket information
bucket_name = "conv_1001"

# Initialize Flask app
app = Flask(__name__)

app.secret_key = 'new_secret_key'

# Allowed file extensions
ALLOWED_EXTENSIONS = {'wav', 'txt', 'mp3'}

# Initialize Google Cloud clients
tts_client = texttospeech.TextToSpeechClient()
storage_client = storage.Client()
lang_service = language_v1.LanguageServiceClient()

# Initialize Vertex AI
vertexai.init(project="my-project-100102", location="us-central1")
model = GenerativeModel("gemini-1.5-flash-001")

# Prompt for transcription and sentiment analysis
prompt = """
Please provide an exact transcript for the audio, followed by sentiment analysis.

Your response should follow the format:

Text: USERS SPEECH TRANSCRIPTION

Sentiment Analysis: positive|neutral|negative
"""

# Helper function to check file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Transcribe audio file from GCS using Vertex AI
def transcribe_gcs(gcs_uri):
    audio_file = Part.from_uri(gcs_uri, mime_type="audio/wav")
    response = model.generate_content([audio_file, prompt])
    return response.text

# Get list of files in the bucket
def get_cloud_files(bucket_name):
    bucket = storage_client.bucket(bucket_name)
    return [blob.name for blob in bucket.list_blobs()]

# Get latest audio and text files from GCS
def get_latest_files_from_gcs():
    bucket = storage_client.bucket(bucket_name)
    blobs = list(bucket.list_blobs())

    audio_files = [blob for blob in blobs if blob.name.endswith(('.wav', '.mp3'))]
    text_files = [blob for blob in blobs if blob.name.endswith('.txt')]

    audio_files.sort(key=lambda x: x.updated, reverse=True)
    text_files.sort(key=lambda x: x.updated, reverse=True)

    latest_audio = audio_files[0].name if audio_files else None
    latest_text = text_files[0].name if text_files else None

    transcription = ""
    if latest_text:
        transcription = bucket.blob(latest_text).download_as_text()

    # Generate signed URL for audio playback
    latest_audio_url = None
    if latest_audio:
        latest_audio_url = bucket.blob(latest_audio).generate_signed_url(version="v4", expiration=3600)

    return latest_audio_url, transcription

# Flask routes
@app.route('/')
def homepage():
    files = get_cloud_files(bucket_name)
    latest_audio_url, transcription = get_latest_files_from_gcs()
    return render_template('index.html', files=files, latest_audio_url=latest_audio_url, transcription=transcription)

@app.route('/upload', methods=['POST'])
def upload_audio():
    if 'audio_data' not in request.files:
        flash('No audio data provided.')
        return redirect(request.url)
    file = request.files['audio_data']
    if file.filename == '':
        flash('No file selected.')
        return redirect(request.url)
    if allowed_file(file.filename):
        filename = "audio_" + datetime.now().strftime("%Y%m%d-%H%M%S") + '.wav'
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        blob.upload_from_file(file, content_type=file.content_type)

        flash('File uploaded successfully to Cloud Storage.')

        gcs_uri = f"gs://{bucket_name}/{filename}"
        transcription_result = transcribe_gcs(gcs_uri)

        text_file_name = filename + ".txt"
        text_blob = bucket.blob(text_file_name)
        text_blob.upload_from_string(transcription_result, content_type="text/plain")

        latest_audio_url = blob.generate_signed_url(version="v4", expiration=3600)

        files = get_cloud_files(bucket_name)
        return render_template('index.html', transcription=transcription_result, files=files, latest_audio_url=latest_audio_url)
    else:
        flash('Invalid file type.')
        return redirect(request.url)

@app.route('/script.js', methods=['GET'])
def serve_script_js():
    return send_file('./script.js')

if __name__ == "_main_":
    app.run(host="0.0.0.0", port=8080)
