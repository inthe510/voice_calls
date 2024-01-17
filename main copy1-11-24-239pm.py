from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory
from datetime import timedelta
import openai
import os
import azure.cognitiveservices.speech as speechsdk
#from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import twilio
from twilio.twiml.voice_response import VoiceResponse
from openai import OpenAI
from azure.cognitiveservices.speech import SpeechConfig, SpeechSynthesizer, AudioConfig
import requests


app = Flask(__name__)

app.secret_key = "hello_world" #os.environ.get("FLASK_SECRET_KEY")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=20)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace("://", "ql://", 1) if os.environ.get('DATABASE_URL') else 'sqlite:///C:/projects/Phone_chatbots/Gabby_V2-VOX-1/data/tmp.db'
app.config['AZURE_SPEEECH_KEY'] = os.environ.get('AZURE_SUBSCRIPTION_KEY')
app.config['AZURE_REGION'] = os.environ.get('AZURE_REGION')


speech_key = os.environ.get('AZURE_SUBSCRIPTION_KEY')
service_region = os.environ.get('AZURE_REGION')
speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)

client = OpenAI()

db = SQLAlchemy(app)

openai.api_key = os.environ.get("OPENAI_API_KEY")

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(512), nullable=False)
    current_scenario = db.Column(db.String(120))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)



class Email(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)

def create_default_admin():
    with app.app_context():
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin')
            admin.set_password('!Gabby2024!')  # Set a strong default password
            db.session.add(admin)
            db.session.commit()


from functools import wraps

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session['username'] != 'admin':
            flash('You need to be logged in as admin to view this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


with app.app_context():
    db.create_all()
    create_default_admin()


# Call the function to ensure the admin user is created on app initialization
#create_default_admin()


system_prompt = "You are a chatbot named Gabby.  Your job is to be a companion and caregiver to an older person. You have a lot of capability in your role as caregiver.  You can offer health and wellness advice, contact service providers like plumbers, meal services and ride services.  You can send and receive messages from family members.  Your dialogues should short and succinct."

default_messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "Hi Gabby"},
    {"role": "assistant", "content": "Good morning. How are you? Did you sleep well last night?  "},

    {"role": "user", "content": "Oh well, no, I didnt. I woke up in the middle of the night and couldnt go back to sleep for a long time."},
    {"role": "assistant", "content": "Sorry to hear that. Do you have anything that worries you?"},

    {"role": "user", "content": "Not really."},
    {"role": "assistant", "content": "Did you take a regular walk yesterday? I think you skipped it."},

    {"role": "user", "content": "Yes, I skipped it because it was too hot outside and my friend didnt show up. Was it bad?  "},
    {"role": "assistant", "content": "Regular exercises will make you sleep better. Try to keep it up. And did you take a regular sleeping pill?"},
    
    {"role": "user", "content": "Oh I forgot.  Thanks for the reminder"},
    {"role": "assistant", "content": "Is it OK with you for now? Or shall I contact your nurse and let her call you?"},

    {"role": "user", "content": "Please greet me and ask how I am doing."},
    ]



@app.route("/twilio-webhook", methods=['POST'])
def twilio_webhook():
    # Twilio sends the speech recording URL
    recording_url = request.values.get('RecordingUrl', '')

    # Process the recording with Azure Speech-to-Text
    user_input = get_text_from_speech(recording_url)

    # Process the input using your chatbot logic
    chatbot_reply = process_chatbot_input(user_input)

    # Convert chatbot reply to speech using Azure TTS
    audio_content = text_to_speech(chatbot_reply)

    # Respond to Twilio with the audio file
    response = VoiceResponse()
    response.play(audio_content)  # Play the Azure TTS audio content
    response.redirect('/twilio-webhook')  # Redirect back for further user input

    return str(response)


def get_text_from_speech(audio_url):
    # Fetch the audio file from the URL
    audio_response = requests.get(audio_url)
    if audio_response.status_code != 200:
        return "Error fetching the audio file"

    # Save the audio file temporarily
    audio_file = "temp_audio.wav"
    with open(audio_file, 'wb') as file:
        file.write(audio_response.content)

    # Set up the Azure STT
    audio_input = speechsdk.AudioConfig(filename=audio_file)
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config, audio_input)

    # Perform the speech recognition
    result = speech_recognizer.recognize_once()

    # Process the result
    if result.reason == speechsdk.ResultReason.RecognizedSpeech:
        return result.text
    elif result.reason == speechsdk.ResultReason.NoMatch:
        return "No speech could be recognized"
    else:
        return "Error recognizing speech"

# Example usage
#transcribed_text = get_text_from_speech("URL_of_the_audio_file_from_Twilio")
#print(transcribed_text)

def text_to_speech(text):
    filename = "chatbot_response.wav"  # Standard filename
    audio_config = AudioConfig(filename=filename)
    synthesizer = SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        return filename
    else:
        return "Error synthesizing speech"


@app.route('/audio-response')
def serve_audio_file():
    filename = "chatbot_response.wav"
    return send_from_directory('C:/projects/Phone_chatbots/Gabby_V2-VOX-1/data/', filename)


def process_chatbot_input(input_text):
    session.permanent = True
    default_messages = []  # Define this as per your requirements

    # Ensure the session has a 'messages' key
    if 'messages' not in session:
        session['messages'] = default_messages.copy()

    # Append the user's input to the session messages
    session['messages'].append({"role": "user", "content": input_text})

    # Get the chatbot's response using OpenAI's API
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=session['messages']
    )
    chatbot_reply = response.choices[0].message.content

    # Append the chatbot's response to the session messages
    session['messages'].append({"role": "assistant", "content": chatbot_reply})
    session.modified = True

    return chatbot_reply










@app.route('/get_azure_keys', methods=['GET'])
def get_azure_keys():
    key = os.environ.get("AZURE_SUBSCRIPTION_KEY")
    region = os.environ.get("AZURE_REGION")
    return jsonify(key=key, region=region)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chatbot')
@admin_required
def chatbot():
    return render_template('chatbot.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/admin')
def admin():
    # Check if user is admin
    if 'username' not in session or session['username'] != 'admin':
        return "Unauthorized", 403

    emails = Email.query.all()
    return render_template('admin.html', emails=emails)


@app.route('/collect_email', methods=['POST'])
def collect_email():
    email = request.form.get('email')
    new_email = Email(email=email)
    db.session.add(new_email)
    db.session.commit()
    return redirect('/')  # or wherever you'd like to redirect after collecting the email

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get username and password from the form
        username = request.form.get('username')
        password = request.form.get('password')

        # Check if the user exists in the database
        user = User.query.filter_by(username=username).first()

        # Check if the password is correct
        if user and user.check_password(password):
            session['username'] = username
            return redirect(url_for('chatbot'))
        else:
            flash('Invalid username/password combination')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    # Remove the username from the session if it's there
    session.pop('username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

"""

@app.route("/twilio-webhook", methods=['POST'])
def twilio_webhook():
    session.permanent = True
    user_input = request.values.get('SpeechResult', '').strip()

    # Reuse your chatbot code to get the chatbot's response
    if 'messages' not in session:
        session['messages'] = default_messages.copy()

    session['messages'].append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model="gpt-4",
        messages=session['messages']
    )
    chatbot_reply = response.choices[0].message.content
    #chatbot_reply = response["choices"][0]["message"]["content"]
    session['messages'].append({"role": "assistant", "content": chatbot_reply})
    session.modified = True

    # Create a TwiML response
    twiml_response = VoiceResponse()
    twiml_response.say(chatbot_reply, voice='alice')

    return str(twiml_response)

@socketio.on('send_message')
def handle_message(data):
    session.permanent = True
    user_input = data['text']

    # Reuse your chatbot code to get the chatbot's response
    if 'messages' not in session:
        session['messages'] = default_messages.copy()

    session['messages'].append({"role": "user", "content": user_input})
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=session['messages']
    )
    chatbot_reply = response["choices"][0]["message"]["content"]
    session['messages'].append({"role": "assistant", "content": chatbot_reply})
    session.modified = True

    print(session['messages'])

    # Emit the result using Socket.IO
    emit('receive_response', {'text': chatbot_reply})





@app.route("/twilio-webhook-OLD", methods=['POST'])
def twilio_webhookold():
    # Parse the incoming call's information from Twilio
    incoming_message = request.values.get('Body', '').strip()

    # Create a TwiML response
    response = VoiceResponse()

    if incoming_message:
        # Respond with a message
        response.say(f"Received your message: {incoming_message}")
    else:
        response.say("Hello, this is your Twilio integration.  You are a sexy motherfucker")

    return str(response)




"""
if __name__ == "__main__":
    app.run(debug=True, port=5001)
