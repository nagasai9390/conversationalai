from flask import Flask, render_template, request, redirect, flash, url_for, send_file, send_from_directory
from werkzeug.utils import secure_filename
from google.cloud import texttospeech, speech, storage, language_v1
from datetime import datetime
import os
import io

# Initialize Flask app and configure directories
app = Flask(__name__)
app.secret_key = 'new_secret_key'
UPLOAD_DIR = 'uploaded_files'
AUDIO_DIR = 'generated_audio'
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'txt'}

app.config['UPLOAD_DIR'] = UPLOAD_DIR
app.config['AUDIO_DIR'] = AUDIO_DIR

# Ensure the directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# Google Cloud clients
tts_client = texttospeech.TextToSpeechClient()
speech_client = speech.SpeechClient()
storage_client = storage.Client()
lang_service = language_v1.LanguageServiceClient()

# Helper function to check allowed extensions
def is_allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Helper function to retrieve files from a directory
def get_file_list(directory):
    return sorted([f for f in os.listdir(directory) if is_allowed_file(f)], reverse=True)

# Function to transcribe audio file
def transcribe_audio(file_path):
    with open(file_path, 'rb') as audio_file:
        audio_content = audio_file.read()

    audio = speech.RecognitionAudio(content=audio_content)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=24000,
        language_code="en-US"
    )

    response = speech_client.recognize(config=config, audio=audio)
    if response.results:
        return response.results[0].alternatives[0].transcript
    return None

# Route to render homepage
@app.route('/')
def homepage():
    uploaded_files = get_file_list(app.config['UPLOAD_DIR'])
    audio_files = get_file_list(app.config['AUDIO_DIR'])
    return render_template('index.html', files=uploaded_files, audios=audio_files)

# Route to handle file uploads
@app.route('/upload', methods=['POST'])
def handle_upload():
    uploaded_file = request.files.get('audio_data')
    if not uploaded_file or uploaded_file.filename == '':
        flash('No file uploaded.')
        return redirect(request.url)

    filename = "audio_" + datetime.now().strftime("%Y%m%d-%H%M%S") + '.wav'
    file_path = os.path.join(app.config['UPLOAD_DIR'], filename)
    uploaded_file.save(file_path)

    # Transcription and sentiment analysis
    transcript = transcribe_audio(file_path)
    if transcript:
        document = language_v1.Document(content=transcript, type_=language_v1.Document.Type.PLAIN_TEXT)
        sentiment_analysis = lang_service.analyze_sentiment(document=document).document_sentiment
        sentiment_result = f"Sentiment: {'positive' if sentiment_analysis.score > 0 else 'negative'}, Score: {sentiment_analysis.score}, Magnitude: {sentiment_analysis.magnitude}"

        # Save the transcript and sentiment result to a file
        text_filename = file_path.replace('.wav', '.txt')
        with open(text_filename, 'w') as txt_file:
            txt_file.write(f"{transcript}\n{sentiment_result}")

        flash('File uploaded and processed successfully.')
    else:
        flash('Could not transcribe the audio file.')

    return redirect(url_for('homepage'))

# Route to serve uploaded files
@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_DIR'], filename)

# Route to handle text input and synthesize speech
@app.route('/upload_text', methods=['POST'])
def synthesize_text():
    text_input = request.form.get('text')
    if not text_input:
        flash('No text provided.')
        return redirect(url_for('homepage'))

    # Text-to-speech synthesis
    input_data = texttospeech.SynthesisInput(text=text_input)
    voice_params = texttospeech.VoiceSelectionParams(language_code='en-US', ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL)
    audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

    response = tts_client.synthesize_speech(input=input_data, voice=voice_params, audio_config=audio_config)
    output_filename = f"tts_{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp3"
    output_filepath = os.path.join(app.config['AUDIO_DIR'], output_filename)
    with open(output_filepath, 'wb') as audio_file:
        audio_file.write(response.audio_content)

    # Perform sentiment analysis
    document = language_v1.Document(content=text_input, type_=language_v1.Document.Type.PLAIN_TEXT)
    sentiment = lang_service.analyze_sentiment(document=document).document_sentiment
    sentiment_result = f"Sentiment: {'positive' if sentiment.score > 0 else 'negative'}, Magnitude: {sentiment.magnitude}, Score: {sentiment.score}"

    flash(f"Text-to-Speech completed and sentiment analyzed: {sentiment_result}")
    return redirect(url_for('homepage'))

# Route to serve synthesized audio files
@app.route('/tts/<filename>')
def serve_audio(filename):
    return send_from_directory(app.config['AUDIO_DIR'], filename, mimetype='audio/mpeg')

if __name__ == '__main__':
    app.run(debug=True)
