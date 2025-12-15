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
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .agent import PodcastQueryAgent
from .config import QueryConfig

console = Console()


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
  
Variables d'environnement requises:
  OPENAI_API_KEY     - Clé API OpenAI
  VOYAGE_API_KEY     - Clé API VoyageAI
  QDRANT_URL         - URL du serveur Qdrant (défaut: http://localhost:6333)
  QDRANT_COLLECTION_NAME - Nom de la collection (défaut: podcasts)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--enable-reranking",
        action="store_true",
        help="Activer le reranking pour une meilleure qualité des réponses (plus lent)",
    )

    args = parser.parse_args()

    # Create configuration
    config = QueryConfig()

    # Apply CLI overrides
    if args.enable_reranking:
        config.use_reranking = True
        console.print("[dim]🔍 Mode qualité: reranking activé[/dim]")

    # Start interactive chat
    await interactive_chat(config)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n👋 Arrêt demandé par l'utilisateur")
    except Exception as e:
        console.print(f"❌ Erreur fatale: {e}", style="red")
        sys.exit(1)
