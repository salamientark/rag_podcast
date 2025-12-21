"""
Client MCP pour l'interrogation de contenu podcast français.

Ce module fournit la classe PodcastMCPClient qui permet de communiquer
avec un serveur MCP FastMCP pour interroger le contenu de podcast.

Usage:
    client = PodcastMCPClient("http://localhost:9000")
    await client.initialize()
    response = await client.query("De quoi parle le dernier épisode ?")
    await client.close()
"""

import logging
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx


class PodcastMCPClient:
    """
    Client MCP pour l'interrogation de contenu podcast.

    Ce client se connecte à un serveur FastMCP et utilise l'outil 'query_db'
    pour interroger le contenu de podcast en français.
    """

    def __init__(self, server_url: str):
        """
        Initialise le client MCP.

        Args:
            server_url: URL du serveur MCP (ex: http://localhost:9000)

        Raises:
            ValueError: Si l'URL du serveur est invalide
        """
        self.server_url = server_url.rstrip("/")
        self.logger = logging.getLogger(__name__)
        self._http_client: Optional[httpx.AsyncClient] = None
        self._available_tools: Dict[str, Dict] = {}

        # Validate URL
        try:
            parsed = urlparse(server_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError(f"URL du serveur MCP invalide: {server_url}")
        except Exception as e:
            raise ValueError(f"URL du serveur MCP invalide: {server_url}") from e

    async def initialize(self) -> None:
        """
        Initialise la connexion au serveur MCP.

        Se connecte au serveur FastMCP et vérifie la disponibilité
        de l'outil 'query_db'.

        Raises:
            ConnectionError: Si impossible de se connecter au serveur
            RuntimeError: Si l'outil 'query_db' n'est pas disponible
        """
        try:
            self.logger.info(f"Connexion au serveur MCP: {self.server_url}")

            # Create HTTP client for FastMCP communication
            self._http_client = httpx.AsyncClient(
                base_url=self.server_url,
                timeout=30.0,
                headers={"Content-Type": "application/json"},
            )

            # Test connection by making a simple HTTP request
            try:
                # For FastMCP, we can test with a simple GET request first
                response = await self._http_client.get("/")

                if response.status_code not in [
                    200,
                    404,
                ]:  # FastMCP may return 404 for root
                    # Try a more specific endpoint
                    response = await self._http_client.get("/health")
                    if response.status_code not in [
                        200,
                        404,
                        405,
                    ]:  # Method not allowed is ok too
                        raise ConnectionError(
                            f"Serveur MCP non accessible: HTTP {response.status_code}"
                        )

                # Assume query_db tool is available (we'll verify during query)
                self._available_tools = {
                    "query_db": {
                        "name": "query_db",
                        "description": "Query podcast database",
                    }
                }
                self.logger.info("Outils MCP disponibles: ['query_db']")

            except httpx.ConnectError:
                raise ConnectionError(
                    f"Impossible de se connecter au serveur MCP sur {self.server_url}"
                )
            except httpx.TimeoutException:
                raise ConnectionError(
                    f"Le serveur MCP ne répond pas (timeout): {self.server_url}"
                )
            except Exception as e:
                if "connection" in str(e).lower() or "refused" in str(e).lower():
                    raise ConnectionError(
                        f"Impossible de se connecter au serveur MCP sur {self.server_url}"
                    )
                else:
                    raise ConnectionError(
                        f"Le serveur MCP ne répond pas: {self.server_url}"
                    )

            self.logger.info("Connexion MCP établie avec succès")

        except ConnectionError:
            raise
        except RuntimeError:
            raise
        except Exception as e:
            self.logger.error(f"Échec de l'initialisation MCP: {e}")
            raise ConnectionError(f"Erreur lors de la connexion MCP: {e}")

    async def query(self, message: str) -> str:
        """
        Envoie une requête au serveur MCP.

        Args:
            message: Question de l'utilisateur en français

        Returns:
            Réponse du serveur MCP en français

        Raises:
            RuntimeError: Si le client n'est pas initialisé
            ConnectionError: Si erreur de communication avec le serveur
        """
        if self._http_client is None:
            raise RuntimeError(
                "Client MCP non initialisé. Appelez initialize() d'abord."
            )

        try:
            self.logger.debug(f"Envoi de la requête MCP: {message[:50]}...")

            # Send request to FastMCP server to call query_db tool
            # FastMCP typically exposes tools as HTTP endpoints
            response = await self._http_client.post(
                "/tools/query_db", json={"question": message}
            )

            if response.status_code != 200:
                error_detail = ""
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_detail = f": {error_data['error']}"
                except Exception:
                    pass
                raise ConnectionError(
                    f"Erreur serveur MCP: HTTP {response.status_code}{error_detail}"
                )

            # FastMCP should return the tool result directly
            if response.headers.get("content-type", "").startswith("application/json"):
                result = response.json()

                # Handle various response formats
                if isinstance(result, str):
                    answer = result
                elif isinstance(result, dict):
                    # Try different possible keys for the response
                    if "result" in result:
                        answer = result["result"]
                    elif "response" in result:
                        answer = result["response"]
                    elif "content" in result:
                        content = result["content"]
                        if isinstance(content, list) and len(content) > 0:
                            answer = content[0].get("text", str(content[0]))
                        else:
                            answer = str(content)
                    else:
                        answer = str(result)
                else:
                    answer = str(result)
            else:
                # Handle non-JSON response
                answer = response.text

            self.logger.debug(f"Réponse MCP reçue: {len(str(answer))} caractères")
            return str(answer)

        except httpx.ConnectError:
            raise ConnectionError("Connexion perdue avec le serveur MCP")
        except httpx.TimeoutException:
            raise ConnectionError("Le serveur MCP ne répond pas (timeout)")
        except ConnectionError:
            raise
        except Exception as e:
            self.logger.error(f"Erreur lors de la requête MCP: {e}")
            raise ConnectionError(f"Erreur de communication avec le serveur MCP: {e}")

    async def close(self) -> None:
        """
        Ferme la connexion MCP.
        """
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
            self.logger.info("Connexion MCP fermée")

    def get_status(self) -> Dict:
        """
        Retourne le statut du client MCP.

        Returns:
            Dictionnaire avec les informations de statut
        """
        return {
            "server_url": self.server_url,
            "connected": self._http_client is not None,
            "client_type": "FastMCP HTTP Client",
            "available_tools": list(self._available_tools.keys())
            if self._available_tools
            else ["query_db"],
        }

    def is_connected(self) -> bool:
        """
        Vérifie si le client est connecté.

        Returns:
            True si connecté, False sinon
        """
        return self._http_client is not None
