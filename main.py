from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.core.lifespan import lifespan
from app.routers.auth import router as auth_router
from app.routers.pages import router as pages_router


app = FastAPI(
    lifespan=lifespan
)
app.include_router(auth_router)
app.include_router(pages_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

if "__main__" == __name__:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=54321)