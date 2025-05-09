document.addEventListener('DOMContentLoaded', () => {
    const audioFileInput = document.getElementById('audioFile');
    const promptTextInput = document.getElementById('promptText');
    const processButton = document.getElementById('processButton');
    const statusMessagesDiv = document.getElementById('statusMessages');
    const audioResultDiv = document.getElementById('audioResult');
    const imageResultDiv = document.getElementById('imageResult');

    // Audio Recording elements
    const startButton = document.getElementById('startButton');
    const stopButton = document.getElementById('stopButton');
    const recordingStatusDiv = document.getElementById('recordingStatus');
    const recordedAudioPlayback = document.getElementById('recordedAudioPlayback');

    let mediaRecorder;
    let audioChunks = [];
    let recordedBlob = null; // To store the final recorded audio Blob

    processButton.addEventListener('click', async () => {
        const promptText = promptTextInput.value.trim();

        let audioFile = null;

        if (recordedBlob) {
            // Use recorded audio if available
            // Create a File object from the Blob
            audioFile = new File([recordedBlob], 'recorded_audio.webm', { type: recordedBlob.type });
            console.log("Using recorded audio blob.", audioFile);
        } else if (audioFileInput.files.length > 0) {
            // Otherwise, use the uploaded file
            audioFile = audioFileInput.files[0];
            console.log("Using uploaded audio file.", audioFile);
        }

        if (!audioFile) {
            displayMessage('Please select or record an audio file.', 'error');
            return;
        }
        if (!promptText) {
            displayMessage('Please enter a processing prompt.', 'error');
            return;
        }

        displayMessage('Processing... Please wait.', 'info');
        processButton.disabled = true;
        audioResultDiv.innerHTML = ''; // Clear previous results
        // Clear previous image results by removing all children
        while (imageResultDiv.firstChild) {
            imageResultDiv.removeChild(imageResultDiv.firstChild);
        }

        const formData = new FormData();
        formData.append('audioFile', audioFile);
        formData.append('promptText', promptText);

        try {
            const response = await fetch('/process_audio', {
                method: 'POST',
                body: formData,
            });

            const result = await response.json();

            if (response.ok && result.processed_files) {
                if (result.processed_files.length > 0) {
                    displayMessage('Processing complete!', 'success');
                    result.processed_files.forEach(fileInfo => {
                        if (fileInfo.type === 'audio' && fileInfo.url) {
                            const audioElement = document.createElement('audio');
                            audioElement.controls = true;
                            audioElement.src = fileInfo.url;
                            const fileLabel = document.createElement('p');
                            fileLabel.textContent = `Processed audio (${fileInfo.filename || 'output'}):`;
                            audioResultDiv.appendChild(fileLabel);
                            audioResultDiv.appendChild(audioElement);
                        } else if (fileInfo.type === 'image' && fileInfo.url) {
                            const imgElement = document.createElement('img');
                            imgElement.src = fileInfo.url;
                            imgElement.alt = `Visualization (${fileInfo.filename || 'output'})`;
                            const imgLabel = document.createElement('p');
                            imgLabel.textContent = `Visualization (${fileInfo.filename || 'output'}):`;
                            imageResultDiv.appendChild(imgLabel);
                            imageResultDiv.appendChild(imgElement);
                        }
                    });
                    if (audioResultDiv.innerHTML === '' && imageResultDiv.innerHTML === '') {
                         displayMessage(result.message || 'Processing completed, but no displayable audio or image output was found.', 'warning');
                    }
                } else {
                    // No files, but potentially a message from the agent (e.g. if it just chatted)
                    displayMessage(result.message || 'Processing completed, but no files were returned.', 'info');
                    if (result.agent_raw_output) {
                        const rawOutputP = document.createElement('p');
                        rawOutputP.innerHTML = `<strong>Agent Response:</strong><br><pre>${escapeHtml(result.agent_raw_output)}</pre>`;
                        statusMessagesDiv.appendChild(rawOutputP);
                    }
                }
            } else {
                const errorMessage = result.error || 'An unknown error occurred during processing.';
                const agentOutput = result.agent_raw_output ? `<br><small>Agent raw output: ${escapeHtml(result.agent_raw_output)}</small>` : '';
                const details = result.details ? `<br><small>Details: ${escapeHtml(JSON.stringify(result.details))}</small>` : '';
                displayMessage(`Error: ${escapeHtml(errorMessage)}${agentOutput}${details}`, 'error');
            }

        } catch (error) {
            console.error('Fetch error:', error);
            displayMessage('A network error occurred. Could not connect to the server.', 'error');
        } finally {
            processButton.disabled = false;
        }
    });

    // Audio Recording Functionality
    startButton.addEventListener('click', async () => {
        audioChunks = []; // Clear previous recording data
        recordedBlob = null; // Clear previous blob
        recordedAudioPlayback.removeAttribute('src'); // Clear previous playback source

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = () => {
                recordedBlob = new Blob(audioChunks, { type: 'audio/webm' }); // Use webm format which is widely supported
                const audioUrl = URL.createObjectURL(recordedBlob);
                recordedAudioPlayback.src = audioUrl;
                recordingStatusDiv.textContent = 'Recording stopped.';
                startButton.disabled = false;
                stopButton.disabled = true;
                // Revoke the object URL after the audio element has loaded it
                recordedAudioPlayback.onloadedmetadata = () => {
                     // URL.revokeObjectURL(audioUrl); // Revoke if memory is a concern and playback is done
                };

                // TODO: Make the recorded audio available for processing. 
                // This might involve creating a File object from the Blob and setting it to audioFileInput or handling it separately.
            };

            mediaRecorder.start();
            recordingStatusDiv.textContent = 'Recording...';
            startButton.disabled = true;
            stopButton.disabled = false;
            audioFileInput.value = ''; // Clear the file input when recording starts
        } catch (err) {
            console.error('Error accessing microphone:', err);
            recordingStatusDiv.textContent = 'Error accessing microphone.';
            displayMessage('Could not access microphone. Please check permissions.', 'error');
            startButton.disabled = false;
            stopButton.disabled = true;
        }
    });

    stopButton.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            // Access the microphone stream and stop all tracks to release the microphone.
            if (mediaRecorder.stream) {
                 mediaRecorder.stream.getTracks().forEach(track => track.stop());
            }
        }
    });

    function displayMessage(message, type) {
        // Create a new paragraph for the message to avoid innerHTML issues with complex strings
        const messageElement = document.createElement('p');
        messageElement.className = type; // Apply class for styling
        messageElement.innerHTML = message; // Use innerHTML as message might contain simple HTML like <br> or <strong>
        statusMessagesDiv.innerHTML = ''; // Clear previous messages
        statusMessagesDiv.appendChild(messageElement);
    }

    function escapeHtml(unsafe) {
        if (typeof unsafe !== 'string') {
            if (unsafe === null || typeof unsafe === 'undefined') return '';
            try {
                unsafe = String(unsafe);
            } catch (e) {
                return '';
            }
        }
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
     }
}); 