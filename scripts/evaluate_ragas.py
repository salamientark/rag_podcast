import os
import json
from dotenv import load_dotenv

from ragas import evaluate
import pandas as pd
from langchain_openai import OpenAIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    Faithfulness,
    AnswerRelevancy,
)

from datasets import Dataset
from langfuse import get_client


DATASET_PATH = "./data/testset.csv"
LIMIT = 10


def _normalize_text(text: str) -> str:
    """
    Normalize text for matching by stripping whitespace and converting to lowercase.

    This ensures that "Who are the co-hosts?" matches "who are the co-hosts? "
    even with case and spacing differences.
    """
    return str(text).strip().lower()


def init_ragas_models() -> tuple:
    """Initialize RAGAS LLM and Embeddings models."""
    load_dotenv()

    try:
        # Init RAGAS llm + embedings for evaluation
        # OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        # eval_llm = ChatOpenAI(model="gpt-5.2", api_key=OPENAI_API_KEY)
        # llm = LangchainLLMWrapper(eval_llm, bypass_n=True)

        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        eval_llm = ChatGoogleGenerativeAI(
            model="gemini-3-pro-preview", api_key=GEMINI_API_KEY
        )
        llm = LangchainLLMWrapper(eval_llm, bypass_n=True)

        # Openai embedding
        lc_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        embedding = LangchainEmbeddingsWrapper(lc_embeddings)

        return llm, embedding
    except Exception as e:
        print(f"Error initializing RAGAS models: {e}")
        return None, None


def _create_dataset_context(langfuse, observations):
    """Helper function to extract context from an observation."""
    contexts = []
    for obs_id in observations:
        obs = langfuse.api.observations.get(observation_id=obs_id)

        # Extract contexts only from observations named "ask_podcast"
        if obs.name == "ask_podcast":
            try:
                # Extract text content from the complex structure
                if isinstance(obs.output, dict):
                    # Try to get structured content result
                    if "structuredContent" in obs.output and isinstance(
                        obs.output["structuredContent"], dict
                    ):
                        if "result" in obs.output["structuredContent"]:
                            contexts.append(
                                str(obs.output["structuredContent"]["result"])
                            )
                            continue

                    # Try to get content text
                    if "content" in obs.output and isinstance(
                        obs.output["content"], list
                    ):
                        for content_item in obs.output["content"]:
                            if (
                                isinstance(content_item, dict)
                                and "text" in content_item
                            ):
                                contexts.append(str(content_item["text"]))
                                continue

                # Fallback - convert the whole structure to a string
                contexts.append(str(obs.output))
            except Exception as e:
                print(f"Error extracting context: {e}")
                # Add a simple placeholder to avoid evaluation failure
                contexts.append("Context extraction failed")

    return contexts


def create_ragas_eval_dataset(langfuse, traces, rows):
    """Fetches traces from Langfuse, extracts questions, answers, and contexts, and compiles them into a rows for RAGAS evaluation."""
    try:
        data = {
            "question": [],
            "answer": [],
            "contexts": [],
            "ground_truth": [],
            "trace_id": [],
        }

        # Create normalized map: normalized_user_input -> row
        row_map = {_normalize_text(row["user_input"]): row for row in rows}

        matched_count = 0
        for trace in traces.data:
            # Extract question from trace (handle different structures)
            trace_question = None
            try:
                if not isinstance(trace.input, str):
                    raise ValueError(f"Trace input is not a string: {trace.input}")
                trace_question = trace.input
            except Exception as e:
                print(f"Error extracting question from trace {trace.id}: {e}")
                continue

            if not trace_question:
                print(f"No question found in trace {trace.id}, skipping")
                continue

            # Normalize and match
            normalized_question = _normalize_text(trace_question)
            if normalized_question not in row_map:
                print(f"Trace question not found in testset: {trace_question[:50]}...")
                continue

            # Get matched row
            row = row_map[normalized_question]

            # Use original (non-normalized) question from trace
            question = trace_question

            # Extract answer
            answer = trace.output
            if isinstance(answer, (list, tuple)):
                if answer and len(answer) > 0:
                    answer = answer[0]

            # Extract ground truth
            ground_truth = row.get("reference")
            if not isinstance(ground_truth, str):
                ground_truth = None

            # Extract contexts from observations
            try:
                contexts = _create_dataset_context(langfuse, trace.observations)
            except Exception as e:
                print(f"Error extracting contexts for trace {trace.id}: {e}")
                contexts = ["Context extraction failed"]
                continue

            # Append to dataset
            data["question"].append(str(question))
            data["answer"].append(answer)
            data["contexts"].append(contexts)
            data["ground_truth"].append(ground_truth)
            data["trace_id"].append(trace.id)

            matched_count += 1
            print(f"✓ Matched trace {trace.id} to question: {question[:50]}...")

        print(f"\nMatched {matched_count} out of {len(traces.data)} traces")
        return data
    except Exception as e:
        print(f"Error creating RAGAS evaluation dataset: {e}")
        return None


def main():
    """Main function to run the RAGAS evaluation."""
    try:
        # 1. Initialize models
        llm, embedding_client = init_ragas_models()
        if llm is None or embedding_client is None:
            os._exit(1)

        # 2. Create evaluation dataset
        # Load CSV and filter to only data columns
        p_data = pd.read_csv(DATASET_PATH)
        # Keep only data columns, exclude metadata
        data_columns = ["user_input", "reference_contexts", "reference"]
        p_data_filtered = p_data[data_columns].copy()
        rows = p_data_filtered.to_dict(orient="records")

        langfuse = get_client()
        traces = langfuse.api.trace.list(limit=LIMIT, order_by="timestamp.desc")
        # traces = langfuse.api.trace.list(limit=row_nbr, order_by="timestamp.desc")

        data = create_ragas_eval_dataset(langfuse, traces, rows)
        if data is None or not data["question"]:
            os._exit(1)
        # 2b. Export dataset to JSON file
        with open("evaluation_data.json", "w") as f:
            json.dump(data, f, indent=2)

        # 3. Score
        dataset = Dataset.from_dict(data)
        # metrics = [Faithfulness(llm=llm), AnswerRelevancy(llm=llm, embeddings=embedding_client)]
        print("Starting RAGAS evaluation...")
        result = evaluate(
            dataset,
            metrics=[
                Faithfulness(llm=llm),
                AnswerRelevancy(llm=llm, embeddings=embedding_client),
            ],
            llm=llm,
            embeddings=embedding_client,
        )
        print("RAGAS evaluation completed. Scores:")
        print(result)

        # 4. Push scores back to Langfuse
        for i, trace_id in enumerate(data["trace_id"]):
            # Safely access results
            faithfulness_score = result["faithfulness"][i]

            langfuse.create_score(
                name="faithfulness",
                value=faithfulness_score,
                trace_id=trace_id,
                data_type="NUMERIC",
            )

            # Answer relevancy might not be available for all entries, so we check before logging
            try:
                answer_relevancy_score = result["answer_relevancy"][i]
                if answer_relevancy_score is not None:
                    langfuse.create_score(
                        name="answer_relevancy",
                        value=answer_relevancy_score,
                        trace_id=trace_id,
                        data_type="NUMERIC",
                    )
            except Exception as e:
                print(f"Answer Relevancy error for trace {trace_id}: {e}")
            print(f"Scores logged for trace {trace_id}.")
            print("-" * 50)

        langfuse.flush()

    except Exception as e:
        print(f"Error during RAGAS evaluation: {e}")
        os._exit(1)


if __name__ == "__main__":
    main()
    os._exit(0)
