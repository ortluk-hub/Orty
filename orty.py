import uvicorn
from service.api import app

if __name__ == "__main__":
    uvicorn.run(
        "service.api:app",
        host="0.0.0.0",
        port=8080,
        reload=False
    )

