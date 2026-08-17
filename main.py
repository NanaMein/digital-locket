from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.lifespan import lifespan
from app.routers import vault

app = FastAPI(lifespan=lifespan)
app.include_router(vault.router)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)