def _speaker_identification_prompt() -> str:
    """
    Returns the prompt template for speaker identification.
    Returns:
        Prompt string
    """
    return (
        "You are a speaker identification assistant. "
        "Given a transcript with generic speaker labels (Speaker A, Speaker B, etc.), "
        "and the episode description that contains context about the speakers, "
        "identify the real names of each speaker based on context clues in the conversation. "
        "If possible use the speaker real name + pseudo if found in the following format: "
        "First name 'Pseudo' Last name. "
        "Return ONLY a valid JSON object mapping each speaker label to their real name. "
        'Format: {"Speaker A": "Name1", "Speaker B": "Name2"}. '
        "If a speaker's name cannot be determined, keep the name as it is."
    )
