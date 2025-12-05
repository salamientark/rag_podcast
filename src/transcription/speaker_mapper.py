import json
from pathlib import Path
from typing import Optional, Dict
from src.llm import _speaker_identification_prompt, init_llm_openai


OPENAI_MODEL = "gpt-5-nano-2025-08-07"

# def estimate_token_count(text: str) -> int:
#     ...
# def extract_episode_id(json_path: Path) -> int:
#     ...
# def build_speaker_prompt(formatted_text: str, speaker_labels: List[str]) -> str:
#     ...


def format_transcript_with_generic_speakers(
    json_path: Path, max_tokens: Optional[int] = None
) -> str:
    """
    Transform Universal-2 JSON transcript to plain text with generic speaker labels.

    Args:
        json_path: Path to transcript JSON file
        max_tokens: Optional token limit for output (None = no limit)

    Returns:
        Formatted string like "Speaker A: ...\n\nSpeaker B: ..."
    """
    try:
        # 1. Load JSON transcript
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 2. Check for diarization
        if not data["speakers"]:
            print("No diarization data found. Returning original transcript.")
            return ""

        # 3. Iterate through text
        words = data["words"]
        speaker = words[0]["speaker"]
        speaker_text = ""
        final_text = ""
        word_count = 0

        for word in words:
            # Speaker change detected
            if word["speaker"] != speaker:
                final_text += f"Speaker {speaker}: {speaker_text}\n\n"
                speaker = word["speaker"]
                speaker_text = ""
            speaker_text += word["text"] + " "

            # Max token reached
            if max_tokens:
                word_count += 1
                if word_count * 0.75 >= max_tokens:
                    break
        final_text += f"Speaker {speaker}: {speaker_text}"
        return final_text
    except Exception as e:
        print(f"Error formatting transcript: {e}")
        return ""


def map_speakers_with_llm(
    formatted_text: str,
) -> Dict[str, str]:
    """
    Use openai llm to map generic speaker labels to real names.

    Args:
        formatted_text: Text with generic labels "Speaker A: ..."

    Returns:
        Mapping like {"A": "Patrick", "B": "Cédric"}
    """
    try:
        # Init llm client
        llm = init_llm_openai()
        if llm is None:
            raise ValueError("LLM client initialization failed.")

        # Ask for speaker mapping
        reponse = llm.responses.create(
            model=OPENAI_MODEL,
            instructions=_speaker_identification_prompt(),
            input=formatted_text,
        )

        result = json.loads(reponse.output_text)
        return result
    except Exception as e:
        print(f"Error during speaker mapping: {e}")
        return {}


def save_speaker_mapping(
    mapping: Dict[str, str], episode_id: int, output_dir: Path = Path("data/speakers")
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
    # Create output directory if not exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save mapping to JSON
    output_path = output_dir / f"episode_{episode_id}_speakers_mapping.json"
    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(mapping, f, indent=4)

    return output_path


ABSOLUTE_TRANSCRIPT_PATH = Path(
    "/home/madlab/Code/rag_podcast/data/transcript/episode_672_universal.json"
)

if __name__ == "__main__":
    txt = format_transcript_with_generic_speakers(ABSOLUTE_TRANSCRIPT_PATH, 10000)
    # print(txt)
    print("Calling map_speakers_with_llm...")
    result = map_speakers_with_llm(txt)
    save_speaker_mapping(result, episode_id=672)
    print("Done")
