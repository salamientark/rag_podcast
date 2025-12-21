"""
MCP CLI interface for podcast queries.

This module provides a French CLI that connects to the MCP server
and provides a stateless chat experience via MCP tools.
"""

import argparse
import asyncio
import logging
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt

from .client import PodcastMCPClient


class MCPChatCLI:
    """
    French CLI interface for MCP-based podcast queries.

    Provides stateless chat experience by calling MCP tools.
    Each query is independent with no conversation memory.
    """

    def __init__(self, mcp_url: str):
        """
        Initialize the MCP CLI.

        Args:
            mcp_url: URL of the MCP server to connect to
        """
        self.mcp_url = mcp_url
        self.client: Optional[PodcastMCPClient] = None
        self.console = Console()
        self.logger = logging.getLogger(__name__)

    async def initialize(self):
        """Initialize the MCP client connection."""
        try:
            self.client = PodcastMCPClient(self.mcp_url)
            await self.client.initialize()
            self.logger.info(f"Connected to MCP server at {self.mcp_url}")
        except Exception as e:
            self.logger.error(f"Failed to connect to MCP server: {e}")
            raise

    async def run(self):
        """Run the interactive French CLI session."""
        if not self.client:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        self._show_welcome()

        try:
            while True:
                try:
                    # Get user input
                    user_input = Prompt.ask("\n[bold blue]Vous[/bold blue]")

                    # Handle special commands
                    if user_input.lower() in ["/quit", "/exit", "/sortir"]:
                        self.console.print("\n[yellow]Au revoir ! 👋[/yellow]")
                        break
                    elif user_input.lower() in ["/help", "/aide"]:
                        self._show_help()
                        continue
                    elif user_input.lower() in ["/status", "/état"]:
                        await self._show_status()
                        continue
                    elif not user_input.strip():
                        continue

                    # Send query to MCP server
                    self.console.print(
                        "\n[dim]Interrogation de la base de données...[/dim]"
                    )
                    response = await self.client.query(user_input)

                    # Display response
                    self.console.print(
                        f"\n[bold green]Assistant[/bold green]: {response}"
                    )

                except KeyboardInterrupt:
                    self.console.print(
                        "\n\n[yellow]Session interrompue. Au revoir ! 👋[/yellow]"
                    )
                    break
                except Exception as e:
                    self.logger.error(f"Error processing query: {e}")
                    self.console.print(f"\n[red]Erreur: {e}[/red]")
                    self.console.print(
                        "[dim]Veuillez réessayer ou tapez /help pour l'aide[/dim]"
                    )

        finally:
            await self.cleanup()

    def _show_welcome(self):
        """Display welcome message."""
        self.console.print("\n" + "=" * 60)
        self.console.print("[bold blue]🎧 Chat Podcast via MCP Server[/bold blue]")
        self.console.print(f"[dim]Connecté à: {self.mcp_url}[/dim]")
        self.console.print("=" * 60)
        self.console.print(
            "\n[green]Posez-moi des questions sur vos épisodes de podcast ![/green]"
        )
        self.console.print(
            "[dim]Mode: Stateless (chaque question est indépendante)[/dim]"
        )
        self.console.print("\n[yellow]Commandes disponibles:[/yellow]")
        self.console.print("  /help, /aide    - Afficher l'aide")
        self.console.print("  /status, /état  - Afficher le statut de la connexion")
        self.console.print("  /quit, /sortir  - Quitter l'application")

    def _show_help(self):
        """Display help information."""
        self.console.print("\n[bold yellow]📚 Aide - Chat Podcast MCP[/bold yellow]")
        self.console.print("\n[green]Comment utiliser:[/green]")
        self.console.print("• Posez des questions en français sur les épisodes")
        self.console.print("• Chaque question est indépendante (pas de mémoire)")
        self.console.print("• Les réponses incluent les références aux épisodes")

        self.console.print("\n[green]Exemples de questions:[/green]")
        self.console.print("• 'De quoi parle le dernier épisode ?'")
        self.console.print("• 'Trouve des épisodes sur l'intelligence artificielle'")
        self.console.print("• 'Qu'est-ce qui a été dit sur les startups ?'")

        self.console.print("\n[green]Commandes:[/green]")
        self.console.print("• /help, /aide    - Cette aide")
        self.console.print("• /status, /état  - Statut de la connexion")
        self.console.print("• /quit, /sortir  - Quitter")

    async def _show_status(self):
        """Display connection and server status."""
        try:
            if not self.client:
                self.console.print("[red]Client non initialisé[/red]")
                return

            status = self.client.get_status()

            self.console.print("\n[bold yellow]📊 Statut de la Connexion[/bold yellow]")
            self.console.print(f"• Serveur MCP: {self.mcp_url}")
            self.console.print(f"• État: {status.get('connection_status', 'Unknown')}")
            self.console.print(
                f"• Outils disponibles: {', '.join(status.get('available_tools', []))}"
            )

            if status.get("connection_status") == "connected":
                self.console.print("[green]✓ Connexion active[/green]")
            else:
                self.console.print("[red]✗ Problème de connexion[/red]")

        except Exception as e:
            self.console.print(
                f"[red]Erreur lors de la vérification du statut: {e}[/red]"
            )

    async def cleanup(self):
        """Clean up resources."""
        if self.client:
            try:
                await self.client.close()
                self.logger.info("MCP client connection closed")
            except Exception as e:
                self.logger.error(f"Error closing client: {e}")


async def main():
    """Main entry point for MCP CLI."""
    parser = argparse.ArgumentParser(
        description="Interface CLI française pour les requêtes podcast via MCP",
        epilog="""
Exemples:
  python -m src.mcp.cli --server-url http://localhost:9000
  python -m src.mcp.cli --server-url http://localhost:9000 --verbose
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--server-url",
        default="http://localhost:9000",
        help="URL du serveur MCP (défaut: http://localhost:9000)",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Activer le logging détaillé"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Create and run CLI
    cli = MCPChatCLI(args.server_url)

    try:
        await cli.initialize()
        await cli.run()
    except Exception as e:
        console = Console()
        console.print(f"[red]Erreur fatale: {e}[/red]")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
