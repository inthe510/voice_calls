

        
        document.addEventListener("DOMContentLoaded", function() {
    fetch('/get_azure_keys')
    .then(response => response.json())
    .then(data => {
        window.azureKey = data.key;
        window.azureRegion = data.region;

        // Initially enable the 'Start Chat' button and disable the 'End Chat' button
        document.getElementById('startButton').disabled = false;
        document.getElementById('stopButton').disabled = true;
    })
    .catch(error => {
        console.error("Error fetching the Azure keys:", error);
        alert("There was an error initializing the application. Please refresh or try again later.");
    });
});

var recognizer;
var synthesizer;
var isChatbotProcessing = false; // Flag to control when the chatbot is allowed to send messages
var isChatActive = false; // Flag to control when the chat is active 

// Create a connection to the server
var socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);

socket.on('receive_response', function(data) {
    document.getElementById('result').innerText = data.text;
    isChatbotProcessing = false; // Reset flag when the response is received
    window.textToSpeech(data.text);
});

function hideInstructions() {
    $(".instructions-container").addClass("hidden");
}

window.startRecording = function() {
    // Set chat state flag
    isChatActive = true;

    // Disable the 'Start Chat' button and enable the 'End Chat' button
    document.getElementById('startButton').disabled = true;
    document.getElementById('stopButton').disabled = false;
    document.getElementById("instructions").classList.add('hidden');
    setPulsingCircleColor('green');

    // Start the recognizer
    startRecognizer();
    
}

window.stopRecording = function() {
    // Unset chat state flag
    isChatActive = false;

    // Re-enable the 'Start Chat' button and disable the 'End Chat' button
    document.getElementById('startButton').disabled = false;
    document.getElementById('stopButton').disabled = true;

    // Stop the recognizer
    recognizer.stopContinuousRecognitionAsync();
}


function playChime() {
    return new Promise((resolve) => {
        var audio = new Audio('static/chime.mp3'); // Update this path to your chime audio file
        audio.addEventListener('ended', resolve);
        audio.play();
    });
}
function estimateSpeechDuration(text) {
    const words = text.split(' ').length;
    const wordsPerMinute = 145;
    return (words / wordsPerMinute) * 60 * 1000; // returns milliseconds
}

function setPulsingCircleColor(color) {
            const circle = document.getElementById('pulsingCircle');
            circle.style.backgroundColor = color;
        }

window.textToSpeech = function(text) {
    // Stop the recognizer
    recognizer.stopContinuousRecognitionAsync();

    // Create a new TTS synthesizer
    var speechConfig = SpeechSDK.SpeechConfig.fromSubscription(window.azureKey, window.azureRegion);
    var audioConfig = SpeechSDK.AudioConfig.fromDefaultSpeakerOutput();
    synthesizer = new SpeechSDK.SpeechSynthesizer(speechConfig, audioConfig);

    synthesizer.speakTextAsync(
        text,
        function (result) {
            if (result.reason === SpeechSDK.ResultReason.SynthesizingAudioCompleted) {
                const estimatedDuration = estimateSpeechDuration(text);
                setPulsingCircleColor('red');
                // Disabling microphone for estimated duration
                // No specific SDK command, so we don't reinitialize the recognizer
                
                // Wait for the estimated duration then play the chime
                setTimeout(async () => {
                    await playChime();
                    setPulsingCircleColor('green');

                    // Re-enable the microphone (Restart the recognizer) only if the chat is still active
                    if (isChatActive) {
                        startRecognizer();
                    }
                }, estimatedDuration);
            }
        },
        function (error) {
            console.error(error);
        }
    );
};

function startRecognizer() {
    var speechConfig = SpeechSDK.SpeechConfig.fromSubscription(window.azureKey, window.azureRegion);
    //speechConfig.speechRecognitionLanguage = "en-EN";
    var audioConfig  = SpeechSDK.AudioConfig.fromDefaultMicrophoneInput();
    recognizer = new SpeechSDK.SpeechRecognizer(speechConfig, audioConfig);

    recognizer.recognizing = function(s, e) {
        document.getElementById('result').innerText = e.result.text;
    };

    recognizer.recognized = function (s, e) {
        if (isChatbotProcessing) {
            return; // If the chatbot is currently processing, exit the function
        }
        
        if (e.result.reason === SpeechSDK.ResultReason.RecognizedSpeech) {
            let text = e.result.text;
            isChatbotProcessing = true; // Set flag when a message is being processed
            recognizer.stopContinuousRecognitionAsync();

            // Send message to the server using Socket.IO
            socket.emit('send_message', { text: text });
        }
    };

    recognizer.startContinuousRecognitionAsync();
}



