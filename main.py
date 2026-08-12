from fastapi import FastAPI

from app.routers import auth, vault

app = FastAPI()
app.include_router(auth.router)
app.include_router(vault.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)