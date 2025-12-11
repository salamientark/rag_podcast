import os
import asyncio
from dotenv import load_dotenv

from pinecone import Pinecone

from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.chat_engine import CondensePlusContextChatEngine
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.postprocessor.cohere_rerank import CohereRerank

from query.prefix import MetadataPrefixPostProcessor

# Constants from other files
# PINECONE_INDEX_NAME = "notpatrick"


# def setup_pinecone_index():
#     """Initializes Pinecone and returns the index object."""
#     api_key = os.getenv("PINECONE_API_KEY")
#     if not api_key:
#         raise ValueError("PINECONE_API_KEY environment variable not set.")
#
#     pc = Pinecone(api_key=api_key)
#
#     if PINECONE_INDEX_NAME not in pc.list_indexes().names():
#         raise ValueError(
#             f"Pinecone index '{PINECONE_INDEX_NAME}' does not exist. Please run the embedding script first."
#         )
#
#     return pc.Index(PINECONE_INDEX_NAME)


async def main():
    """Main function to run the CLI chat agent."""
    load_dotenv()

    # Configure core LlamaIndex settings
    Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-large")
    llm = OpenAI(model="gpt-4o")
    Settings.llm = llm

    cohere_api_key = os.getenv("COHERE_API_KEY")
    if not cohere_api_key:
        print("Warning: COHERE_API_KEY not found. Reranking will be disabled.")
        cohere_rerank = None
    else:
        cohere_rerank = CohereRerank(api_key=cohere_api_key, top_n=3)

    # Initialize Pinecone
    pinecone_index = setup_pinecone_index()
    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index,
        text_key="chunk_text",
    )
    index = VectorStoreIndex.from_vector_store(vector_store)

    # Postprocessor to add metadata to the context
    metadata_postprocessor = MetadataPrefixPostProcessor(meta_key="episode_date")

    # Setup node postprocessors - order matters!
    # 1. Rerank to get the most relevant nodes
    # 2. Add metadata to the text of the reranked nodes
    node_postprocessors = []
    if cohere_rerank:
        node_postprocessors.append(cohere_rerank)
    node_postprocessors.append(metadata_postprocessor)

    # Setup memory for chat history
    memory = ChatMemoryBuffer.from_defaults(token_limit=3000)

    # Setup chat engine
    chat_engine = CondensePlusContextChatEngine.from_defaults(
        retriever=index.as_retriever(similarity_top_k=10),
        node_postprocessors=node_postprocessors,
        memory=memory,
        system_prompt="""Vous êtes un assistant conçu pour répondre aux questions sur le podcast 'Not Patrick'.
Utilisez les informations pertinentes des épisodes du podcast pour fournir une réponse complète et conversationnelle.
Chaque information est précédée de sa date d'épisode. Utilisez cette date pour contextualiser votre réponse.
Ne vous contentez pas de répéter le texte brut des sources.
Si vous ne trouvez pas d'information pertinente, indiquez que vous n'avez pas pu trouver l'information dans le podcast.
Soyez amical et engageant.""",
    )

    print("\nWelcome to the Not Patrick podcast query agent!")
    print("Ask me anything about the podcast. Type 'exit' or press Ctrl+C to quit.\n")

    while True:
        try:
            user_query = await asyncio.to_thread(input, "You: ")
            if user_query.lower() in ["exit", "quit"]:
                break

            if not user_query.strip():
                continue

            print("Agent is thinking...")
            response = await chat_engine.achat(user_query)
            print(f"Agent: {response}\n")

        except (KeyboardInterrupt, EOFError):
            break

    print("\nGoodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except ValueError as e:
        print(f"Error: {e}")
