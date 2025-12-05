import json
import logging
from pathlib import Path
from typing import Optional, Dict

from src.llm import _speaker_identification_prompt, init_llm_openai
from src.logger import setup_logging, log_function


OPENAI_MODEL = "gpt-5-nano-2025-08-07"

# def extract_episode_id(json_path: Path) -> int:
#     ...


@log_function(logger_name="speaker_mapper", log_args=True, log_execution_time=True)
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
    logger = logging.getLogger("speaker_mapper")

    try:
        # 1. Load JSON transcript
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error(f"Transcript file not found: {json_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in transcript file: {e}")
        raise

    try:
        # 2. Check for diarization
        if not data["speakers"]:
            logger.warning("No diarization data found. Returning original transcript.")
            return ""

        # 3. Iterate through text
        words = data["words"]
        if not words:
            logger.warning("No word data found in transcript.")
            return ""

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
    except (KeyError, IndexError) as e:
        logger.error(f"Missing expected fields in transcript data: {e}")
        raise


@log_function(logger_name="speaker_mapper", log_execution_time=True)
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
    logger = logging.getLogger("speaker_mapper")

    try:
        # Init llm client
        llm = init_llm_openai()
        if llm is None:
            raise ValueError("LLM client initialization failed.")

        # Ask for speaker mapping
        logger.info("Calling LLM for speaker identification")
        response = llm.responses.create(
            model=OPENAI_MODEL,
            instructions=_speaker_identification_prompt(),
            input=formatted_text,
        )

        result = json.loads(response.output_text)
        logger.info(f"LLM returned speaker mapping: {result}")
        return result
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        return {}
    except AttributeError as e:
        logger.error(f"Invalid LLM API call: {e}")
        return {}
    except (ValueError, KeyError) as e:
        logger.error(f"Error in LLM processing: {e}")
        return {}


@log_function(logger_name="speaker_mapper", log_args=True, log_execution_time=True)
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
    logger = logging.getLogger("speaker_mapper")

    try:
        # Create output directory if not exists
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create output directory {output_dir}: {e}")
        raise

    # Save mapping to JSON
    output_path = output_dir / f"episode_{episode_id}_speakers_mapping.json"
    try:
        with open(
            output_path,
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(mapping, f, indent=4)
        logger.info(f"Saved speaker mapping to {output_path}")
    except OSError as e:
        logger.error(f"Failed to write speaker mapping to {output_path}: {e}")
        raise

    return output_path


# ========= TESTING BEGIN ==========
ABSOLUTE_TRANSCRIPT_PATH = Path(
    "/home/madlab/Code/rag_podcast/data/transcript/episode_672_universal.json"
)

if __name__ == "__main__":
    # Setup logging
    logger = setup_logging(
        logger_name="speaker_mapper", log_file="logs/speaker_mapper.log", verbose=True
    )

    logger.info("Starting speaker mapping process")
    txt = format_transcript_with_generic_speakers(ABSOLUTE_TRANSCRIPT_PATH, 10000)
    # print(txt)
    logger.info("Calling map_speakers_with_llm...")
    result = map_speakers_with_llm(txt)
    save_speaker_mapping(result, episode_id=672)
    logger.info("Speaker mapping completed successfully")

# ========== TESTING END ===========
