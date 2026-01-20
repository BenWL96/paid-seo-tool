import os
import asyncio
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from google import genai
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page
from pydantic import BaseModel, HttpUrl
from bs4 import BeautifulSoup
from typing import Optional

# ----------------------------
# REQUEST MODELS
# ----------------------------
class BannerConfig(BaseModel):
    type: str
    text: str

class AskRequest(BaseModel):
    url: HttpUrl
    banner_1: Optional[BannerConfig] = None
    banner_2: Optional[BannerConfig] = None


# ----------------------------
# APP SETUP
# ----------------------------
load_dotenv()

app = FastAPI()

client = genai.Client(
    api_key=os.environ.get("GOOGLE_API_KEY"),
    vertexai=False
)

DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

ROOT_DIR = Path(__file__).resolve().parent

NON_SEO_TAGS = [
    "script", "style", "nav", "footer", "header", "aside",
    "noscript", "svg", "iframe", "form", "button", "input",
    "textarea", "select", "option", "canvas", "meta", "link"
]

search_tool = genai.types.Tool(
    google_search=genai.types.GoogleSearch()
)

# ----------------------------
# BANNER HANDLING
# ----------------------------
def accept_banner(page: Page, banner: BannerConfig, timeout: int = 5000) -> bool:
    selectors = [
        f"button:has-text('{banner.text}')",
        f"[role='button']:has-text('{banner.text}')",
        f"[aria-label*='{banner.text}']",
    ]

    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=timeout)
            return True
        except:
            pass

    for frame in page.frames:
        for selector in selectors:
            try:
                frame.locator(selector).first.click(timeout=2000)
                return True
            except:
                pass

    try:
        page.evaluate(
            """
            (text) => {
                const btn = [...document.querySelectorAll("button")]
                  .find(b => b.innerText.toLowerCase().includes(text.toLowerCase()));
                if (btn) btn.click();
            }
            """,
            banner.text
        )
        return True
    except:
        return False


# ----------------------------
# PAGE LOAD PIPELINE
# ----------------------------
def prepare_page(page: Page, url: str, banner_1, banner_2):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_selector("body", timeout=10000)

    if banner_1:
        accept_banner(page, banner_1)
        time.sleep(0.5)

    if banner_2:
        accept_banner(page, banner_2)
        time.sleep(0.5)


# ----------------------------
# SCRAPER (SCREENSHOTS + CLEAN HTML)
# ----------------------------
def capture_screenshots_and_html(url: str, banner_1, banner_2):
    screenshots = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        desktop_context = browser.new_context(viewport=DESKTOP_VIEWPORT)
        desktop_page = desktop_context.new_page()
        prepare_page(desktop_page, url, banner_1, banner_2)

        screenshots.append(desktop_page.screenshot(full_page=True))
        raw_html = desktop_page.content()

        mobile_context = browser.new_context(
            viewport=MOBILE_VIEWPORT,
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3
        )
        mobile_page = mobile_context.new_page()
        prepare_page(mobile_page, url, banner_1, banner_2)

        screenshots.append(mobile_page.screenshot(full_page=True))

        browser.close()

    # -------- HTML CLEANING --------
    soup = BeautifulSoup(raw_html, "html.parser")
    body = soup.body

    if not body:
        raise ValueError("No <body> tag found")

    for tag_name in NON_SEO_TAGS:
        for tag in body.find_all(tag_name):
            tag.decompose()

    cleaned_html = body.get_text(separator="\n", strip=True)

    return screenshots, cleaned_html


# ----------------------------
# FASTAPI ENDPOINT
# ----------------------------
@app.post("/ask")
async def ask_gemini(body: AskRequest):
    try:
        screenshots, cleaned_html = await asyncio.to_thread(
            capture_screenshots_and_html,
            str(body.url),
            body.banner_1,
            body.banner_2,
        )
        filenames = [
            ROOT_DIR / "screenshot_desktop.png",
            ROOT_DIR / "screenshot_mobile.png",
        ]

        image_parts = []

        for img_bytes, path in zip(screenshots, filenames):
            path.write_bytes(img_bytes)
            image_parts.append(
                genai.types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/png"
                )
            )  

        print(cleaned_html)
        exit()

        response = await client.aio.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                "Analyze the following ecommerce product page HTML and screenshots. "
                "Describe how the product page could be improved for UX, SEO, and conversion.",
                f"HTML CONTENT:\n{cleaned_html}",
                *image_parts
            ],
            config=genai.types.GenerateContentConfig(
                tools=[search_tool]
            )
        )

        return {
            "response": response.text,
            "saved_files": [p.name for p in filenames],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ----------------------------
# LOCAL RUN
# ----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
