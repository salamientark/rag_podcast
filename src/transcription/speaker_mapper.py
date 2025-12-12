import json
import logging
from pathlib import Path
from typing import Optional, Dict

from src.llm import _speaker_identification_prompt, init_llm_openai
from src.logger import setup_logging, log_function


OPENAI_MODEL = "gpt-5"


def _apply_speaker_mapping(
    speaker: str, speaker_mapping: Optional[Dict[str, str]]
) -> str:
    """
    Apply speaker mapping to convert generic label to real name.

    Args:
        speaker: Generic speaker label like "A", "B", "C"
        speaker_mapping: Optional mapping dict

    Returns:
        Mapped name or generic label "Speaker X"
    """
    generic_label = f"Speaker {speaker}"

    if not speaker_mapping:
        return generic_label

    # Check if mapping exists for this speaker
    if generic_label in speaker_mapping:
        mapped_value = speaker_mapping[generic_label]
        # If value is "unknown" (case-insensitive), keep generic label
        if mapped_value.lower() == "unknown":
            return generic_label
        return mapped_value

    return generic_label


@log_function(logger_name="speaker_mapper", log_args=True, log_execution_time=True)
def format_transcript(
    json_path: Path,
    max_tokens: Optional[int] = None,
    speaker_mapping: Optional[Dict[str, str]] = None,
) -> str:
    """
    Transform Universal-2 JSON transcript to plain text with generic speaker labels.

    Args:
        json_path: Path to transcript JSON file
        max_tokens: Optional token limit for output (None = no limit)
        speaker_mapping: Optional dict mapping generic labels to real names.
                        Format: {"Speaker A": "John Doe", "Speaker B": "unknown"}
                        If value is "unknown" (case-insensitive), keeps generic label.

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
                # Apply speaker mapping if provided
                speaker_label = _apply_speaker_mapping(speaker, speaker_mapping)
                final_text += f"{speaker_label}: {speaker_text}\n\n"
                speaker = word["speaker"]
                speaker_text = ""
            speaker_text += word["text"] + " "

            # Max token reached
            if max_tokens:
                word_count += 1
                if word_count * 0.75 >= max_tokens:
                    break

        # Apply mapping to final speaker
        speaker_label = _apply_speaker_mapping(speaker, speaker_mapping)
        final_text += f"{speaker_label}: {speaker_text}"
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


@log_function(logger_name="speaker_mapper", log_execution_time=True)
def get_mapped_transcript(raw_transcript_path: Path) -> str:
    """Get formatted transcript with mapped speaker names.

    Args:
        raw_transcript_path: Path to raw transcript JSON file
    Returns:
        Formatted transcript with real speaker names
    """
    # Init logger
    logger = logging.getLogger("speaker_mapper")

    logger.info("Formatting raw transcript...")
    raw_text = format_transcript(raw_transcript_path, max_tokens=10000)
    logger.info("Mapping speakers with LLM...")
    speaker_mapping = map_speakers_with_llm(raw_text)
    logger.info("Re-formatting transcript with mapped speaker names...")
    final_text = format_transcript(raw_transcript_path, speaker_mapping=speaker_mapping)
    logger.info("Transcript formatting complete.")
    return final_text


# ========= TESTING BEGIN ==========
ABSOLUTE_TRANSCRIPT_PATH = Path(
    "./data/transcript/episode_672_universal.json"
)

if __name__ == "__main__":
    # Setup logging
    logger = setup_logging(
        logger_name="speaker_mapper", log_file="logs/speaker_mapper.log", verbose=True
    )

    logger.info("Starting speaker mapping process")
    txt = format_transcript(ABSOLUTE_TRANSCRIPT_PATH, 10000)
    # print(txt)
    logger.info("Calling map_speakers_with_llm...")
    result = map_speakers_with_llm(txt)
    save_speaker_mapping(result, episode_id=672)
    logger.info("Speaker mapping completed successfully")

# ========== TESTING END ===========
