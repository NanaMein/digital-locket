from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse

router = APIRouter()
# Tell FastAPI where your HTML files are
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def welcome_page(request: Request):
    return templates.TemplateResponse(request,"index.html")

@router.post("/verify")
async def verify_passphrase(request: Request):
    # You'll add your logic to check the passphrase here!
    # If correct, redirect to the dashboard
    return RedirectResponse(url="/dashboard", status_code=303)

@router.get("/dashboard")
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")