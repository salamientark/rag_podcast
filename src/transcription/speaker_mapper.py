import json
from pathlib import Path
from typing import Optional


# def estimate_token_count(text: str) -> int:
#     ...
# def extract_episode_id(json_path: Path) -> int:
#     ...
# def build_speaker_prompt(formatted_text: str, speaker_labels: List[str]) -> str:
#     ...

def format_transcript_with_generic_speakers(
    json_path: Path,
    max_tokens: Optional[int] = None
) -> str:
    """
    Transform Universal-2 JSON transcript to plain text with generic speaker labels.
    
    Args:
        json_path: Path to transcript JSON file
        max_tokens: Optional token limit for output (None = no limit)
        
    Returns:
        Formatted string like "Speaker A: ...\n\nSpeaker B: ..."
    """
    # 1. Load JSON transcript
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 2. Check for diarization
    if not data['speakers']:
        print("No diarization data found. Returning original transcript.")
        return ""

    # 3. Iterate throught text
    words = data['words']
    speaker = words[0]['speaker']
    speaker_text = ""
    final_text = ""

    # token limit
    if max_tokens:
        word_count = 0

    for word in words:
        # Speaker change detected
        if word['speaker'] != speaker:
            final_text += f"Speaker {speaker}: {speaker_text}\n\n"
            speaker = word['speaker']
            speaker_text = ""
        speaker_text += word['text'] + " "
        word_count += 1

        # Max token reached
        if max_tokens and word_count * 0.75 >= max_tokens:
            final_text += f"Speaker {speaker}: {speaker_text}"
            break
    return final_text


def map_speakers_with_llm(
    formatted_text: str,
    model: str = "llama3.2:3b",
    ollama_url: str = "http://localhost:11434"
) -> Dict[str, str]:
    """
    Use LLM to map generic speaker labels to real names.
    
    Args:
        formatted_text: Text with generic labels "Speaker A: ..."
        model: Ollama model name
        ollama_url: Ollama API endpoint
        
    Returns:
        Mapping like {"A": "Patrick", "B": "Cédric"}
    """
    pass


def save_speaker_mapping(
    mapping: Dict[str, str],
    episode_id: int,
    output_dir: Path = Path("data/speakers")
) -> Path:
    """
    Save speaker mapping to JSON file.
    
    Args:
        mapping: Speaker label to name mapping
        episode_id: Episode number
        output_dir: Directory to save mapping files
        
    Returns:
        Path to saved JSON file
    """
    pass


ABSOLUTE_TRANSCRIPT_PATH="/home/madlab/Code/rag_podcast/data/transcript/episode_672_universal.json"

if __name__ == "__main__":
    txt = format_transcript_with_generic_speakers(ABSOLUTE_TRANSCRIPT_PATH, 1000)
    print(txt)
