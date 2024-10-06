from pathlib import Path

from server.config import Settings
from server.server import app

__all__ = ["app"]

if __name__ == "__main__":
    import uvicorn

    module = Path(__file__).stem
    uvicorn.run(
        f"{module}:app",
        host="0.0.0.0",
        port=8000,
        reload=Settings.testing,
        # access_log=False,
        workers=Settings.testing and 1 or 4,
    )
