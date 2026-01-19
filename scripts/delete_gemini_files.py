import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

# Configure client
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

print("Listing files...")
files = list(client.files.list())

print(f"Found {len(files)} files. Deleting...")

for f in files:
    try:
        print(f"Deleting {f.name}...")
        client.files.delete(name=f.name)
    except Exception as e:
        print(f"Failed to delete {f.name}: {e}")

print("Cleanup complete.")
