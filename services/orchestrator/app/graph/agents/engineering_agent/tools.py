from langchain_core.tools import tool
from ....core.config import SERVICE_HEALTH_URLS
import httpx
@tool
async def check_service_status(service_name:str)-> str:
    """
    Check the live health status of a specific internal service.

    Use this only when the user asks for a service's current
    health/status (e.g. "is retrieval-service up", "check ingestion
    service health"). Do NOT use this to stop, redeploy, or scale a
    service - this tool can only report status.
    """
    base_url = SERVICE_HEALTH_URLS.get(service_name)
    if not base_url:
        return f"Unknown service {service_name!r}. Known services: {', '.join(SERVICE_HEALTH_URLS)}."
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base_url}/health")
            response.raise_for_status()
    except httpx.RequestError:
        return f"Service {service_name} is down (unreachable)."
    except httpx.HTTPStatusError as e:
        return f"Service {service_name} is unhealthy (HTTP {e.response.status_code})."

    return f"Your service with name {service_name} status is good"
