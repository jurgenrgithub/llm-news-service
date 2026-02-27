"""Health check endpoint"""

from fastapi import APIRouter
from core.database import get_connection
from core.claude_client import ClaudeClient

router = APIRouter()


@router.get("/health")
def health_check():
    """Check service health including database and Claude CLI"""
    status = {
        "status": "healthy",
        "database": "unknown",
        "claude_cli": "unknown",
    }

    # Check database
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        status["database"] = "connected"
    except Exception as e:
        status["database"] = f"error: {str(e)[:100]}"
        status["status"] = "unhealthy"

    # Check Claude CLI
    try:
        client = ClaudeClient()
        response = client.query("Reply with just OK")
        if response.is_error:
            status["claude_cli"] = f"error: {response.error_message}"
            status["status"] = "unhealthy"
        else:
            status["claude_cli"] = "available"
    except Exception as e:
        status["claude_cli"] = f"error: {str(e)[:100]}"
        status["status"] = "unhealthy"

    return status
