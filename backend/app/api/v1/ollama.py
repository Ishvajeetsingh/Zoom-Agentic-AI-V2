from fastapi import APIRouter
import httpx

from app.core.config import settings

router = APIRouter(
    prefix="/ollama",
    tags=["Ollama"],
)


@router.get("/status")
async def ollama_status():
    """
    Returns whether Ollama is running and
    which models are currently available.
    """

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{settings.ollama_base_url}/api/tags"
            )

        if response.status_code != 200:
            return {
                "online": False,
                "models": [],
            }

        return {
            "online": True,
            "models": response.json().get("models", []),
        }

    except Exception:
        return {
            "online": False,
            "models": [],
        }