import os
import argparse
import json
import sys
from dotenv import load_dotenv
from google import genai

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
)

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PROMPT = """
You are an expert in audio transcription. Given an audio file provide a precise transcription in the same language as the audio.

## INPUT:

- A podcast audio file.

## TRANSCRIPTION INSTRUCTIONS

- Identify speaker and map them to their names if possible, otherwise use generic labels like Speaker_A, Speaker_B, etc.
- Include timestamps in [HH:MM:SS] format at the start of each speaker turn

"""


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio using Eleven Labs API"
    )
    parser.add_argument("input", type=str, help="Path to the audio file to transcribe")
    args = parser.parse_args()

    try:
        if not os.path.exists(args.input):
            raise FileNotFoundError(f"Input file not found: {args.input}")

        print(f"Uploading audio file: {args.input}")
        audio_file = client.files.upload(file=args.input)
        print("Starting transcription")
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=[PROMPT, audio_file],
        )
        print("Transcription completed")

        print(response)

        os.makedirs("tmp", exist_ok=True)
        with open("tmp/gemini_transcript_text.txt", "w") as f:
            f.write(response.text)
            print("Wrote transcript text to tmp/gemini_transcript_text.txt")

        with open("tmp/gemini_transcript.json", "w") as f:
            json.dump(response, f, indent=4)
            print("Wrote full transcript JSON to tmp/gemini_transcript.json")
    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
