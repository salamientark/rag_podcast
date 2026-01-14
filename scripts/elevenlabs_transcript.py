# example.py
import os
from dotenv import load_dotenv
import argparse
from elevenlabs.client import ElevenLabs


load_dotenv()

client = ElevenLabs(
    api_key=os.getenv("ELEVENLABS_API_KEY"),
)


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio using Eleven Labs API"
    )
    parser.add_argument("input", type=str, help="Path to the audio file to transcribe")
    args = parser.parse_args()

    with open(args.input, "rb") as audio_file:
        transcription = client.speech_to_text.convert(
            file=audio_file,
            model_id="scribe_v2",  # The current transcription model
            tag_audio_events=True,  # Tags things like (laughter), (applause)
            diarize=True,  # Identifies different speakers
        )
    print(transcription)

    os.makedirs("tmp", exist_ok=True)
    with open("tmp/elevenlab_transcript_text.txt", "w") as f:
        f.write(transcription.text)
        print("Wrote transcript text to tmp/elevenlab_transcript_text.txt")

    import json

    with open("tmp/elevenlab_transcript.json", "w") as f:
        json.dump(transcription.model_dump(), f, indent=4)
        print("Wrote full transcript JSON to tmp/elevenlab_transcript.json")


if __name__ == "__main__":
    main()
