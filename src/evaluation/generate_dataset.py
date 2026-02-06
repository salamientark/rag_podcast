import os
import argparse
from dotenv import load_dotenv
from pathlib import Path
from typing import List, Optional, Dict, Any
from llama_index.core import Document
from langchain_core.documents import Document as LCDocument
from src.chunker import chunk_long_text

from llama_index.llms.anthropic import Anthropic
from llama_index.embeddings.voyageai import VoyageEmbedding
from ragas.testset import TestsetGenerator

from src.logger import setup_logging
from src.db import get_db_session, get_podcast_by_name_or_slug, Episode
from src.storage.cloud import CloudStorage
from src.query import QueryConfig

logger = setup_logging(
    logger_name="reprocess_failed",
    log_file="logs/reprocess_failed.log",
    verbose=True,
)

# Document chunking parameters
EVAL_CHUNK_SIZE = 1024
EVAL_OVERLAP = 0.1


def parse_args():
    parser = argparse.ArgumentParser(description="Generate RAG evaluation dataset")
    parser.add_argument(
        "--podcast", type=str, required=True, help="Name or slug of the podcast"
    )
    parser.add_argument(
        "--limit", type=int, default=10, help="Number of episodes to process"
    )
    return parser.parse_args()


def filter_episodes(
    podcast_name: str, limit: int = 10
) -> Optional[List[Dict[str, Any]]]:
    """
    Retrieve the latest episodes for a given podcast that have a formatted transcript.

    Args:
        podcast_name:(str) The name or slug of the podcast.
        limit(int): The maximum number of episodes to return. Defaults to 10.

    Returns:
        A list of episode dictionaries if successful, or None if the podcast
        is not found or an error occurs.
    """
    try:
        # Check for podcast existence
        podcast = get_podcast_by_name_or_slug(podcast_name)
        if not podcast:
            raise ValueError(f"Podcast '{podcast_name}' not found.")
        # Get the lasts episode from podcast
        episode_as_dicts = []
        with get_db_session() as session:
            episodes_to_process = (
                session.query(Episode)
                .filter(
                    Episode.podcast_id == podcast.id,
                    Episode.formatted_transcript_path.isnot(None),
                )
                .order_by(Episode.published_date.desc())
                .limit(limit)
                .all()
            )
            episode_as_dicts = [ep.to_dict() for ep in episodes_to_process]
        return episode_as_dicts
    except Exception as e:
        logger.error(f"Error fetching podcast '{podcast_name}': {e}")
        return None


def load_documents_from_url(file_urls: List[str]) -> List[Document]:
    """
    Load and chunk documents from a list of url.

    Args:
        file_url: List of url to transcript files.

    Returns:
        List of LlamaIndex Document objects with chunked content and metadata.
    """
    documents = []

    # We use a smaller chunk size for evaluation dataset generation
    # to create more specific questions.

    for file_url in file_urls:
        try:
            text = CloudStorage.get_transcript_content_from_url(file_url)

            if not text.strip():
                logger.warning(f"Empty file skipped: {file_url}")
                continue

            # Create chunks
            chunks = chunk_long_text(
                text, max_tokens=EVAL_CHUNK_SIZE, overlap_percent=EVAL_OVERLAP
            )

            # Extract some basic metadata from filename if possible
            filename = Path(file_url).name

            # Convert chunks to LlamaIndex Documents
            for i, chunk_text in enumerate(chunks):
                metadata = {
                    "source": str(file_url),
                    "filename": filename,
                    "chunk_index": i,
                }

                doc = Document(text=chunk_text, metadata=metadata)
                documents.append(doc)

            logger.info(f"Loaded {len(chunks)} chunks from {filename}")

        except Exception as e:
            logger.error(f"Error loading {file_url}: {e}")

    return documents


def init_test_set_generator() -> Optional[TestsetGenerator]:
    try:
        load_dotenv()
        global_config = QueryConfig()

        ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is not set in environment variables.")
        generator_llm = Anthropic(
            model=global_config.llm_model,
            api_key=global_config.anthropic_api_key,
            system_prompt="You are a strict dataset generator. You must output only valid JSON. Do not output any conversational text, preambles, or explanations.",
        )
        embedding_model = VoyageEmbedding(
            voyage_api_key=global_config.voyage_api_key,
            model_name=global_config.embedding_model,
            output_dimension=global_config.embedding_dimensions,
        )

        generator = TestsetGenerator.from_llama_index(
            llm=generator_llm,
            embedding_model=embedding_model,
        )
        return generator
    except Exception as e:
        logger.error(f"Error initializing TestsetGenerator: {e}")
        return None


def __main__():
    """ """
    args = parse_args()
    try:
        # Get the last episodes with formatted transcripts for the specified podcast
        logger.info(
            f"Fetching episodes for podcast: {args.podcast} with limit: {args.limit}"
        )
        episodes_as_dict = filter_episodes(args.podcast, args.limit)
        if episodes_as_dict is None:
            logger.error("Failed to fetch episodes.")
            return

        logger.info(
            f"Fetched {len(episodes_as_dict)} episodes for podcast: {args.podcast}"
        )
        logger.info(f"Episodes IDS: {[ep['episode_id'] for ep in episodes_as_dict]}")

        transcripts_path = [ep["formatted_transcript_path"] for ep in episodes_as_dict]

        # Load documents
        logger.info("Loading documents from transcripts paths...")
        documents = load_documents_from_url(transcripts_path)
        if not documents:
            raise ValueError("No documents loaded from transcripts.")
        logger.info(f"Loaded {len(documents)} documents from transcripts.")

        # Initialize the test set generator
        logger.info("Initializing TestsetGenerator...")
        generator = init_test_set_generator()
        if generator is None:
            raise ValueError("Failed to initialize TestsetGenerator.")
        logger.info("TestsetGenerator initialized successfully.")

        # Create the test set
        logger.info("Generating test set...")

        # Convert LlamaIndex documents to LangChain documents for generate_with_chunks
        # This bypasses the problematic HeadlinesExtractor which is redundant for pre-chunked data
        langchain_docs = [
            LCDocument(page_content=doc.text, metadata=doc.metadata)
            for doc in documents
        ]

        test_set = generator.generate_with_chunks(
            chunks=langchain_docs,
            testset_size=50,
        )

        print("Generated Test Set:")
        print(test_set)

        # Export to CSV using pandas
        try:
            logger.info("Exporting test set to CSV...")
            df = test_set.to_pandas()
            output_path = "data/testset.csv"
            df.to_csv(output_path, index=False)
            logger.info(f"Test set saved to {output_path}")
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")

    except Exception as e:
        logger.error(f"Error in main: {e}")
        exit(1)


if __name__ == "__main__":
    __main__()
