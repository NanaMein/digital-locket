from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import vault

app = FastAPI()
app.include_router(vault.router)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)