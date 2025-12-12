# LLM Module

LLM integration layer providing abstractions for different language models and AI services used throughout the RAG podcast system.

## Quick Start

```python
from src.llm.openai import OpenAIClient
from src.llm.base import LLMProvider

# OpenAI integration
client = OpenAIClient()
response = client.generate_completion("Summarize this podcast episode...")
```

## Components

### Base Classes (`base.py`)
- **`LLMProvider`** - Abstract base class for LLM integrations
- **Common interfaces** - Standardized methods across different providers
- **Configuration management** - Unified settings and parameters

### OpenAI Integration (`openai.py`)
- **OpenAI API client** - GPT-4 and GPT-3.5 integration
- **Chat completions** - Conversational AI for speaker identification
- **Text generation** - Content processing and analysis
- **Error handling** - Rate limiting and API error management

## Features

- **Provider abstraction** - Easy switching between different LLM providers
- **Consistent API** - Same interface across different models
- **Configuration management** - Environment-based settings
- **Error handling** - Robust error handling with retries
- **Usage tracking** - Token counting and cost estimation

## Usage Examples

### Speaker Identification

The LLM module is primarily used for speaker identification in transcripts:

```python
# Through the transcription system (automatic)
uv run -m src.transcription

# The LLM analyzes speaker patterns and identifies real names
# Input: "Speaker A: Welcome to the show... Speaker B: Thanks Patrick..."
# Output: {"Speaker A": "Patrick", "Speaker B": "Guest"}
```

### Direct LLM Usage

```python
from src.llm.openai import OpenAIClient

client = OpenAIClient()

# Text analysis
result = client.analyze_content(
    text="Podcast transcript content...",
    prompt="Identify the main topics discussed"
)

# Chat-based interaction  
response = client.chat_completion([
    {"role": "system", "content": "You are a podcast analyst"},
    {"role": "user", "content": "What are the key insights?"}
])
```

## Configuration

Environment variables:
```bash
# OpenAI
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4  # or gpt-3.5-turbo

# Optional settings
LLM_TEMPERATURE=0.1     # Lower for consistent outputs
LLM_MAX_TOKENS=1000     # Response length limit
```

## Provider Support

### Currently Implemented
- **OpenAI** - GPT-4, GPT-3.5-turbo for speaker identification

### Planned Extensions
- **Anthropic Claude** - Alternative provider for analysis tasks
- **Local models** - Ollama integration for privacy-focused deployments
- **Azure OpenAI** - Enterprise deployments

## Integration Points

The LLM module integrates with:

1. **Transcription Module** - Speaker name identification from transcript context
2. **Query System** - RAG responses and conversation handling  
3. **Pipeline System** - Automated content analysis and processing

## Speaker Identification Process

The core LLM use case in this system:

1. **Input**: Raw transcript with generic speaker labels (Speaker A, Speaker B)
2. **Analysis**: LLM analyzes conversation context and speaker patterns
3. **Identification**: Maps generic labels to real names based on context clues
4. **Output**: Speaker mapping dictionary for transcript formatting

## Error Handling

```python
try:
    result = client.generate_completion(prompt)
except RateLimitError:
    # Automatic retry with exponential backoff
    pass
except APIError as e:
    # Log error and fallback to generic speaker labels
    logger.error(f"LLM API error: {e}")
```

## Best Practices

1. **Prompt engineering** - Clear, specific prompts for consistent results
2. **Temperature settings** - Lower values (0.1-0.3) for factual tasks
3. **Token management** - Monitor usage and implement limits
4. **Fallback handling** - Graceful degradation when LLM unavailable
5. **Caching** - Store results to avoid redundant API calls

## Cost Optimization

- **Efficient prompts** - Minimize token usage with clear, concise prompts
- **Batch processing** - Group multiple requests when possible
- **Result caching** - Store speaker mappings to avoid re-identification
- **Model selection** - Use appropriate model size for the task complexity