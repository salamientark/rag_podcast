"""
French CLI interface for the podcast query agent.

This module provides an interactive French chat interface using Rich for
beautiful terminal output. Users can query their podcast content in French
and get conversational responses with source citations.

Usage:
    uv run -m src.query
"""

import argparse
import asyncio
import sys
import logging
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.chat_engine import CondensePlusContextChatEngine
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.llms.anthropic import Anthropic
from llama_index.embeddings.voyageai import VoyageEmbedding
from qdrant_client import QdrantClient, AsyncQdrantClient

from .config import QueryConfig, SYSTEM_PROMPT_FR
from .postprocessors import get_reranker


console = Console()


class PodcastQueryAgent:
    """
    Main query agent for podcast content using LlamaIndex and VoyageAI.

    Integrates with existing Qdrant vector store containing VoyageAI embeddings
    and provides a French chat interface with optional reranking.
    """

    def __init__(self, config: QueryConfig):
        """
        Initialize the podcast query agent.

        Args:
            config: QueryConfig instance with all settings

        Raises:
            ConnectionError: If unable to connect to Qdrant
            ValueError: If API keys are missing
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        try:
            self._validate_config()
            self._setup_models()
            self._setup_vector_store()
            self._setup_chat_engine()
            self.logger.info("Podcast query agent initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize query agent: {e}")
            raise

    def _validate_config(self):
        """Validate required configuration and API keys"""
        if not self.config.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")

        if not self.config.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY is required")

    def _setup_models(self):
        """Configure LLM and embedding models"""
        # VoyageAI embeddings (compatible with existing vectors)
        Settings.embed_model = VoyageEmbedding(
            voyage_api_key=self.config.voyage_api_key,
            model_name=self.config.embedding_model,
            output_dimension=self.config.embedding_dimensions,
        )

        # Anthropic Claude LLM
        Settings.llm = Anthropic(
            model=self.config.llm_model, api_key=self.config.anthropic_api_key
        )

        self.logger.info(
            f"Models configured: {self.config.llm_model} + {self.config.embedding_model}"
        )

    def _setup_vector_store(self):
        """Initialize Qdrant vector store connection"""
        try:
            # Use sync client for initial connection test
            sync_client = QdrantClient(
                url=self.config.qdrant_url, api_key=self.config.qdrant_api_key
            )

            # Test connection by checking if collection exists
            collections = sync_client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.config.collection_name not in collection_names:
                raise ConnectionError(
                    f"Collection '{self.config.collection_name}' not found. "
                    f"Available: {collection_names}"
                )

            # Create async client for vector store
            async_client = AsyncQdrantClient(
                url=self.config.qdrant_url, api_key=self.config.qdrant_api_key
            )

            # Create vector store
            # Create vector store with both sync and async clients
            self.vector_store = QdrantVectorStore(
                client=sync_client,  # Sync client for query operations
                aclient=async_client,  # Async client for async operations
                collection_name=self.config.collection_name,
            )

            # Create index from existing vectors
            self.index = VectorStoreIndex.from_vector_store(self.vector_store)

            self.logger.info(
                f"Connected to Qdrant collection: {self.config.collection_name}"
            )

        except Exception as e:
            self.logger.error(f"Failed to connect to Qdrant: {e}")
            raise ConnectionError(
                f"Cannot connect to Qdrant at {self.config.qdrant_url}: {e}"
            )

    def _setup_chat_engine(self):
        """Configure chat engine with postprocessors and memory"""
        # Build postprocessor pipeline (order matters!)
        postprocessors = []

        # 1. Optional reranking with BGE-M3 (French-optimized)
        if self.config.use_reranking:
            reranker = get_reranker(
                model_name=self.config.rerank_model, top_n=self.config.rerank_top_n
            )
            postprocessors.append(reranker)
            self.logger.info(f"Reranking enabled with {self.config.rerank_model}")
        else:
            self.logger.info("Reranking disabled (faster responses)")

        # Note: We'll handle metadata injection manually in the query method

        # Conversation memory
        memory = ChatMemoryBuffer.from_defaults(
            token_limit=self.config.memory_token_limit
        )

        # Create chat engine
        self.chat_engine = CondensePlusContextChatEngine.from_defaults(
            retriever=self.index.as_retriever(
                similarity_top_k=self.config.similarity_top_k
            ),
            node_postprocessors=postprocessors,
            memory=memory,
            system_prompt=SYSTEM_PROMPT_FR,
        )

        self.logger.info(
            f"Chat engine configured: top_k={self.config.similarity_top_k}, "
            f"memory={self.config.memory_token_limit} tokens"
        )

    async def query(self, message: str) -> str:
        """
        Process a user query and return a response.

        Args:
            message: User's question in French

        Returns:
            Agent's response in French

        Raises:
            Exception: If query processing fails
        """
        try:
            self.logger.debug(f"Processing query: {message[:50]}...")
            response = await self.chat_engine.achat(message)
            self.logger.debug(f"Generated response: {len(str(response))} characters")
            return str(response)

        except Exception as e:
            self.logger.error(f"Query processing failed: {e}")
            raise

    def get_status(self) -> dict:
        """
        Get agent status and configuration info.

        Returns:
            Dictionary with agent status information
        """
        return {
            "collection_name": self.config.collection_name,
            "qdrant_url": self.config.qdrant_url,
            "llm_model": self.config.llm_model,
            "embedding_model": self.config.embedding_model,
            "reranking_enabled": self.config.use_reranking,
            "rerank_model": self.config.rerank_model
            if self.config.use_reranking
            else None,
            "memory_limit": self.config.memory_token_limit,
        }


async def interactive_chat_mcp(mcp_server_url: str):
    """
    Main interactive chat loop using MCP client.

    Args:
        mcp_server_url: URL of the MCP server
    """
    try:
        # Dynamic import to avoid import errors at module level
        import importlib.util
        import os

        # Get the path to the MCP client module
        mcp_client_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "mcp", "client.py"
        )

        # Load the module dynamically
        spec = importlib.util.spec_from_file_location("mcp_client", mcp_client_path)
        if spec is None or spec.loader is None:
            raise ImportError("Impossible de charger le module MCP client")
        mcp_client_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mcp_client_module)

        PodcastMCPClient = mcp_client_module.PodcastMCPClient

        # Initialize MCP client
        console.print("[dim]🔧 Initialisation du client MCP...[/dim]")
        agent = PodcastMCPClient(mcp_server_url)
        await agent.initialize()

        # Display status
        status = agent.get_status()
        status_text = f"📊 Connecté au serveur MCP: {status['server_url']}"
        console.print(f"[dim]{status_text}[/dim]")
        console.print()

        # Welcome message
        print_welcome()

        # Chat loop
        while True:
            try:
                user_input = input("\033[1;32mVous:\033[0m ")

                if not user_input.strip():
                    continue

                if user_input.lower() in ["/quit", "/q", "exit", "quit"]:
                    break

                if user_input.lower() in ["/help", "/h", "help"]:
                    show_help()
                    continue

                # Process query via MCP
                console.print("[dim]🤔 L'agent réfléchit...[/dim]")

                try:
                    response = await agent.query(user_input)
                    console.print(f"[bold blue]Agent:[/bold blue] {response}")
                    console.print()

                except Exception as e:
                    console.print(f"❌ Erreur lors du traitement: {e}", style="red")
                    console.print("[dim]Veuillez réessayer ou taper /help[/dim]")
                    console.print()

            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                console.print(f"❌ Erreur inattendue: {e}", style="red")
                console.print("[dim]Tapez /quit pour quitter[/dim]")

        console.print("\n👋 À bientôt!")

        # Close MCP client
        await agent.close()

    except ConnectionError as e:
        console.print(f"❌ Erreur MCP: {e}", style="red")
        console.print("\n💡 Vérifications:")
        console.print("  • Le serveur MCP est-il démarré ?")
        console.print(
            "  • Commande: uv run -m src.mcp.server --host 127.0.0.1 --port 9000"
        )
        console.print(f"  • Le serveur répond-il sur {mcp_server_url} ?")
        sys.exit(1)

    except Exception as e:
        console.print(f"❌ Erreur fatale MCP: {e}", style="red")
        sys.exit(1)


def print_welcome():
    """Display welcome message in French with usage instructions"""
    welcome_text = Text()
    welcome_text.append("🎧 Agent de Requête Podcast\n", style="bold blue")
    welcome_text.append("Posez-moi des questions sur vos épisodes !", style="italic")

    console.print(Panel(welcome_text, title="Bienvenue", border_style="blue"))
    console.print("💡 Tapez '/help' pour l'aide ou '/quit' pour quitter")
    console.print()


def show_help():
    """Display help information in French"""
    help_text = """
🎧 Agent de Requête Podcast - Aide

UTILISATION:
  • Tapez votre question en français
  • L'agent cherchera dans tous vos épisodes de podcast
  
COMMANDES:
  • /help - Afficher cette aide
  • /quit - Quitter l'application

EXEMPLES DE QUESTIONS:
  • "De quoi parle le dernier épisode ?"
  • "Quels sujets ont été abordés récemment ?"
  • "Que dit l'animateur sur l'intelligence artificielle ?"
  • "Résume-moi les points importants sur Google"
  • "Quelles sont les nouveautés mentionnées ?"

L'agent citera toujours ses sources avec le titre et numéro d'épisode.
"""
    console.print(Panel(help_text, title="Aide", border_style="green"))


async def interactive_chat(config: QueryConfig):
    """
    Main interactive chat loop.

    Args:
        config: QueryConfig instance with all settings
    """
    try:
        # Initialize agent
        console.print("[dim]🔧 Initialisation de l'agent...[/dim]")
        agent = PodcastQueryAgent(config)

        # Display status
        status = agent.get_status()
        status_text = (
            f"📊 Connecté à '{status['collection_name']}' avec {status['llm_model']}"
        )
        if status["reranking_enabled"]:
            status_text += f" + reranking {status['rerank_model']}"
        console.print(f"[dim]{status_text}[/dim]")
        console.print()

        # Welcome message
        print_welcome()

        # Chat loop
        while True:
            try:
                user_input = input("\033[1;32mVous:\033[0m ")

                if not user_input.strip():
                    continue

                if user_input.lower() in ["/quit", "/q", "exit", "quit"]:
                    break

                if user_input.lower() in ["/help", "/h", "help"]:
                    show_help()
                    continue

                # Process query
                console.print("[dim]🤔 L'agent réfléchit...[/dim]")

                try:
                    response = await agent.query(user_input)
                    console.print(f"[bold blue]Agent:[/bold blue] {response}")
                    console.print()

                except Exception as e:
                    console.print(f"❌ Erreur lors du traitement: {e}", style="red")
                    console.print("[dim]Veuillez réessayer ou taper /help[/dim]")
                    console.print()

            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                console.print(f"❌ Erreur inattendue: {e}", style="red")
                console.print("[dim]Tapez /quit pour quitter[/dim]")

        console.print("\n👋 À bientôt!")

    except ConnectionError as e:
        console.print(f"❌ Erreur de connexion: {e}", style="red")
        console.print("\n💡 Vérifications:")
        console.print(f"  • Qdrant est-il démarré ? ({config.qdrant_url})")
        console.print(f"  • La collection '{config.collection_name}' existe-t-elle ?")
        console.print("  • Les clés API sont-elles configurées ?")
        sys.exit(1)

    except ValueError as e:
        console.print(f"❌ Configuration manquante: {e}", style="red")
        console.print("\n💡 Ajoutez les clés API requises à votre fichier .env:")
        console.print("  • OPENAI_API_KEY=your_key_here")
        console.print("  • VOYAGE_API_KEY=your_key_here")
        sys.exit(1)

    except Exception as e:
        console.print(f"❌ Erreur fatale: {e}", style="red")
        sys.exit(1)


async def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description="Agent de requête pour podcast français",
        epilog="""
Exemples:
  uv run -m src.query
  uv run -m src.query --enable-reranking
  uv run -m src.query --mcp-server-url http://localhost:9000
  
Variables d'environnement requises (mode direct):
  OPENAI_API_KEY     - Clé API OpenAI
  VOYAGE_API_KEY     - Clé API VoyageAI
  QDRANT_URL         - URL du serveur Qdrant (défaut: http://localhost:6333)
  QDRANT_COLLECTION_NAME - Nom de la collection (défaut: podcasts)
  
Mode MCP:
  Pour utiliser le mode MCP, démarrez d'abord le serveur MCP:
  uv run -m src.mcp.server --host 127.0.0.1 --port 9000
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--enable-reranking",
        action="store_true",
        help="Activer le reranking pour une meilleure qualité des réponses (plus lent)",
    )

    parser.add_argument(
        "--mcp-server-url",
        type=str,
        help="URL du serveur MCP (utilise le client MCP au lieu de l'agent direct)",
    )

    args = parser.parse_args()

    # Check if MCP mode is requested
    if args.mcp_server_url:
        # Start MCP client mode
        console.print(f"[dim]🌐 Mode MCP activé: {args.mcp_server_url}[/dim]")
        await interactive_chat_mcp(args.mcp_server_url)
    else:
        # Create configuration for direct agent mode
        config = QueryConfig()

        # Apply CLI overrides
        if args.enable_reranking:
            config.use_reranking = True
            console.print("[dim]🔍 Mode qualité: reranking activé[/dim]")

        # Start interactive chat with direct agent
        await interactive_chat(config)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n👋 Arrêt demandé par l'utilisateur")
    except Exception as e:
        console.print(f"❌ Erreur fatale: {e}", style="red")
        sys.exit(1)
