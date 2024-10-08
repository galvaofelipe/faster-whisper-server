import os
from pathlib import Path
import subprocess
import threading

import httpx
import keyboard

# NOTE: this is a very basic implementation. Not really meant for usage by others.
# Included here in case someone wants to use it as a reference.

# This script will run in the background and listen for a keybind to start recording audio.
# It will then wait until the keybind is pressed again to stop recording.
# The audio file will be sent to the server for transcription.
# The transcription will be copied to the clipboard.
# When having a short audio of a couple of sentences and running inference on a GPU the response time is very fast (less than 2 seconds).  # noqa: E501

CHUNK = 2**12
AUDIO_RECORD_CMD = [
    "ffmpeg",
    # "-hide_banner",
    # "-loglevel",
    # "quiet",
    "-f",
    "alsa",
    "-i",
    "default",
    "-f",
    "wav",
    # "-ac",
    # "1",
    # "-ar",
    # "16000",
    # "-f",
    # "s16le",
    # "-acodec",
    # "pcm_s16le",
    # "-",
]
COPY_TO_CLIPBOARD_CMD = "wl-copy"
OPENAI_BASE_URL = "ws://localhost:8000/v1"
TRANSCRIBE_PATH = "/audio/transcriptions?language=en"
USER = "nixos"
TIMEOUT = httpx.Timeout(None)
KEYBIND = "ctrl+x"
LANGUAGE = "en"
RESPONSE_FORMAT = "text"

client = httpx.Client(base_url=OPENAI_BASE_URL, timeout=TIMEOUT)
is_running = threading.Event()
file = Path("test.wav")  # TODO: use tempfile


while True:
    keyboard.wait(KEYBIND)
    print("Action started")
    process = subprocess.Popen(
        [*AUDIO_RECORD_CMD, "-y", str(file.name)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        user=USER,
        env=dict(os.environ),
    )
    keyboard.wait(KEYBIND)
    process.kill()
    print("Action finished")

    with open(file, "rb") as f:
        res = client.post(
            OPENAI_BASE_URL + TRANSCRIBE_PATH,
            files={"file": f},
            data={
                "response_format": RESPONSE_FORMAT,
                "language": LANGUAGE,
            },
        )
        transcription = res.text
        print(transcription)
        subprocess.run([COPY_TO_CLIPBOARD_CMD], input=transcription.encode(), check=True)
