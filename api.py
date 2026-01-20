import os
import asyncio
from io import BytesIO
from fastapi import FastAPI, HTTPException
from google import genai
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from PIL import Image
from pydantic import BaseModel, HttpUrl

class AskRequest(BaseModel):
    url: HttpUrl

load_dotenv()

app = FastAPI()

# Gemini async client
client = genai.Client(
    api_key=os.environ.get("GOOGLE_API_KEY"),
    vertexai=False
)

DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}
MOBILE_VIEWPORT = {"width": 390, "height": 844}


# ----------------------------
# BLOCKING SCRAPER (THREAD SAFE)
# ----------------------------
def capture_screenshots(url: str) -> list[bytes]:
    screenshots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ---------- DESKTOP ----------
        desktop_context = browser.new_context(viewport=DESKTOP_VIEWPORT)
        desktop_page = desktop_context.new_page()
        desktop_page.goto(url, wait_until="domcontentloaded", timeout=60000)

        screenshots.append(
            desktop_page.screenshot(full_page=True)
        )

        # ---------- MOBILE ----------
        mobile_context = browser.new_context(
            viewport=MOBILE_VIEWPORT,
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3
        )
        mobile_page = mobile_context.new_page()
        mobile_page.goto(url, wait_until="domcontentloaded", timeout=60000)

        screenshots.append(
            mobile_page.screenshot(full_page=True)
        )

        browser.close()

    return screenshots


@app.post("/ask")
async def ask_gemini(body: AskRequest):
    try:
        screenshots = await asyncio.to_thread(
            capture_screenshots,
            str(body.url)
        )

        image_parts = [
            genai.types.Part.from_bytes(
                data=img,
                mime_type="image/png"
            )
            for img in screenshots
        ]

        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                "Analyze these ecommerce screenshots and describe the product page.",
                *image_parts
            ]
        )

        return {"response": response.text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# LOCAL RUN
# ----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

