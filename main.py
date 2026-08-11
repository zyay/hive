"""Hive — entry point. Run with: python main.py or uvicorn hive.api.main:app"""

import uvicorn
from hive.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "hive.api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )
