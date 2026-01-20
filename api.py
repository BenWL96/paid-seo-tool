import os
import asyncio
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from google import genai
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page
from pydantic import BaseModel, HttpUrl
from bs4 import BeautifulSoup, Comment, NavigableString
from typing import Optional
import re



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





# ------------------------------
# HTML SCRAPING & EXTRACTION
# ------------------------------

DEFAULT_HEADERS = {
    "User-Agent": "benswebservice-scraper/1.0 (+https://benswebservice.co.uk)"
}


def fetch_html(url, timeout=10):
    response = requests.get(url, timeout=timeout, headers=DEFAULT_HEADERS)
    response.raise_for_status()
    return response.text


def strip_class_and_id(soup):
    NON_EXECUTIVE_ATTRS = {
        # --- Styling / layout (non-SEO) ---
        "class",
        "id",
        "style",
        "width",
        "height",
        "align",
        "valign",
        "border",


        # --- Image / media rendering ---
        "src",
        "srcset",
        "sizes",
        "loading",
        "decoding",
        "fetchpriority",
        "poster",

        # --- Performance / hints ---
        "importance",
        "inert",
        "blocking",

        # --- JS / behaviour hooks ---
        "onclick",
        "onload",
        "onerror",
        "onmouseover",
        "onmouseenter",
        "onmouseleave",
        "onfocus",
        "onblur",
        "onchange",
        "onsubmit",

        # --- Framework / hydration noise ---
        "slot",
        "is",
        "key",
        "ref",
        "part",
        "exportparts",

        # --- Tracking / marketing ---
        "ping",
        "target",
        "data-track",
        "data-tracking",
        "data-testid",

        # --- Misc non-semantic ---
        "tabindex",
        "contenteditable",
        "spellcheck",
        "draggable",
        "translate",
    }


    # Remove HTML comments
    for comment in soup.find_all(
        string=lambda text: isinstance(text, Comment)
    ):
        comment.extract()

    # Remove unwanted attributes
    for tag in soup.find_all(True):  # True = all tags
        for attr in list(tag.attrs):
            if attr in NON_EXECUTIVE_ATTRS or attr.startswith("data-"):
                tag.attrs.pop(attr, None)

    return str(soup)



def remove_html_whitespace(html):
    soup = BeautifulSoup(html, "html.parser")

    for element in soup.find_all(string=True):
        # Remove whitespace-only text nodes
        if isinstance(element, NavigableString) and not element.strip():
            element.extract()

    # Return fully minified HTML
    return soup.decode(formatter="minimal")


MAX_HTML_CHARS = 50_000

# --- MODE 1: Keep structured data ---
REMOVE_TAGS_LIGHT = [
    "noscript", "template",
    "style", "link",
    "svg", "path", "defs", "symbol", "use",
    "head", "meta", "base", "title",
    "header", "footer", "nav", "aside",
    "form", "input", "textarea", "select",
    "option", "button", "label", "fieldset", "legend",
    "canvas", "video", "audio", "source", "track",
    "iframe", "embed", "object", "param",
    "colgroup", "col", "tbody", "thead", "tfoot",
    "details", "summary", "dialog",
    "map", "area",
]

# --- MODE 2: Aggressive stripping (no schema) ---
REMOVE_TAGS_AGGRESSIVE = [
    "script", "noscript", "template",
    "style", "link",
    "svg", "path", "defs", "symbol", "use",
    "head", "meta", "base", "title",
    "header", "footer", "nav", "aside",
    "form", "input", "textarea", "select",
    "option", "button", "label", "fieldset", "legend",
    "canvas", "video", "audio", "source", "track",
    "iframe", "embed", "object", "param",
    "colgroup", "col", "tbody", "thead", "tfoot",
    "details", "summary", "dialog",
    "map", "area",
]


def extract_tagged_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    head = soup.head

    if not head:
        return ""

    print(head)
    exit()

    body = soup.body

    if not body:
        return ""

    # ----------------------------
    # PASS 1: Preserve structured data
    # ----------------------------
    for script in body.find_all("script"):
        script_type = (script.get("type") or "").lower()
        if script_type not in ("application/ld+json", "application/json"):
            script.decompose()

    for bad in body.find_all(REMOVE_TAGS_LIGHT):
        bad.decompose()

    html_with_structure_data = strip_class_and_id(body)
    html_no_whitespace = remove_html_whitespace(html_with_structure_data)

    # # ----------------------------
    # # SIZE CHECK
    # # ----------------------------
    # if len(html_no_whitespace) <= MAX_HTML_CHARS:
    #     return html_no_whitespace

    # # ----------------------------
    # # PASS 2: Aggressive fallback
    # # ----------------------------
    # soup = BeautifulSoup(html, "html.parser")
    # body = soup.body

    # if not body:
    #     return ""

    # for bad in body.find_all(REMOVE_TAGS_AGGRESSIVE):
    #     bad.decompose()

    # cleaned_html = strip_class_and_id(body) 

    # html_no_whitespace = remove_html_whitespace(cleaned_html)


    return html_no_whitespace


# Includes all schema
# def extract_tagged_text(html):
#     soup = BeautifulSoup(html, "html.parser")
#     body = soup.body

#     if not body:
#         return ""

#     # 1️⃣ Remove non-structured scripts ONLY
#     for script in body.find_all("script"):
#         script_type = (script.get("type") or "").lower()

#         if script_type not in (
#             "application/ld+json",
#             "application/json",
#         ):
#             script.decompose()

#     # 2️⃣ Remove all other unwanted tags
#     for bad in body.find_all(REMOVE_TAGS):
#         bad.decompose()

#     # 3️⃣ Optional: strip attributes
#     cleaned_html = strip_class_and_id(body)

#     print(cleaned_html)
#     exit()

#     # 4️⃣ Normalize whitespace
#     html_no_whitespace = remove_html_whitespace(cleaned_html)
#     return html_no_whitespace




DESKTOP_VIEWPORT = {"width": 1920, "height": 1080}
MOBILE_VIEWPORT = {"width": 390, "height": 844}

ROOT_DIR = Path(__file__).resolve().parent


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

        context = browser.new_context(
            viewport=DESKTOP_VIEWPORT,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()
        prepare_page(page, url, banner_1, banner_2)

        # ----------------------------
        # JS SITE DETECTION
        # ----------------------------
        html_initial = page.content()
        initial_length = len(html_initial)

        # Wait briefly to allow JS hydration
        page.wait_for_timeout(1500)

        html_after_wait = page.content()
        after_wait_length = len(html_after_wait)

        is_js_site = after_wait_length > initial_length * 1.1

        # ----------------------------
        # IF JS SITE → RENDER FULL DOM
        # ----------------------------
        if is_js_site:
            # Attempt scroll to trigger lazy loading / hydration
            page.mouse.wheel(0, 5000)
            page.wait_for_timeout(2000)

        # Capture final HTML
        raw_html = page.content()

        # Screenshot desktop
        screenshots.append(page.screenshot(full_page=True))

        # ----------------------------
        # MOBILE PASS (NO RE-DETECTION)
        # ----------------------------
        mobile_context = browser.new_context(
            viewport=MOBILE_VIEWPORT,
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3,
            user_agent=(
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            )
        )

        mobile_page = mobile_context.new_page()
        prepare_page(mobile_page, url, banner_1, banner_2)

        if is_js_site:
            mobile_page.wait_for_timeout(1500)
            mobile_page.mouse.wheel(0, 4000)
            mobile_page.wait_for_timeout(1500)

        screenshots.append(mobile_page.screenshot(full_page=True))

        browser.close()

    cleaned_html = extract_tagged_text(raw_html)


    return screenshots, cleaned_html


    
# ----------------------------
# CONCURRENCY LIMITS
# ----------------------------

MAX_CONCURRENT_REQUESTS = 4        # overall API load
MAX_PLAYWRIGHT_SESSIONS = 1        # Chromium is expensive

request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
playwright_semaphore = asyncio.Semaphore(MAX_PLAYWRIGHT_SESSIONS)


# ----------------------------
# FASTAPI ENDPOINT
# ----------------------------
@app.post("/premium/audit")
async def ask_gemini(body: AskRequest):
    async with request_semaphore:
        try:
            # Limit Playwright usage separately
            async with playwright_semaphore:
                screenshots, cleaned_html = await asyncio.to_thread(
                    capture_screenshots_and_html,
                    str(body.url),
                    body.banner_1,
                    body.banner_2,
                )

            image_parts = []
            for img_bytes in screenshots:
                image_parts.append(
                    genai.types.Part.from_bytes(
                        data=img_bytes,
                        mime_type="image/png"
                    )
                )
            # Save in project root (or change this path if you want)
            # output_dir = Path(".").resolve()

            # filenames = [
            #     output_dir / "screenshot_desktop.png",
            #     output_dir / "screenshot_mobile.png",
            # ]

            # for img_bytes, path in zip(screenshots, filenames):
            #     # ✅ Save image to disk
            #     path.write_bytes(img_bytes)

            #     # ✅ Pass image to Gemini
            #     image_parts.append(
            #         genai.types.Part.from_bytes(
            #             data=img_bytes,
            #             mime_type="image/png"
            #         )
            #     )

            # Gemini call can safely run concurrently
            # Split up mobile and desktop analysis
            # Model should be able to identify page intent from HTML alone..
            desktop_response = await client.aio.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    "Analyze the following ecommerce product page HTML and screenshots. "
                    "Describe how the product page could be improved for UX, SEO, and conversion on DESKTOP DISPLAY ONLY.",
                    f"HTML CONTENT:\n{cleaned_html}",
                    *image_parts
                ],
                config=genai.types.GenerateContentConfig(
                    tools=[search_tool]
                )
            )

            # Gemini call can safely run concurrently
            mobile_response = await client.aio.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    "Analyze the following ecommerce product page HTML and screenshots. "
                    "Describe how the product page could be improved for UX, SEO, and conversion on MOBILE DISPLAY ONLY.",
                    f"HTML CONTENT:\n{cleaned_html}",
                    *image_parts
                ],
                config=genai.types.GenerateContentConfig(
                    tools=[search_tool]
                )
            )

            # Gemini call can safely run concurrently
            aeo_response = await client.aio.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    "Analyze the following ecommerce product page HTML and screenshots. "
                    "Describe how the product page data could be improved for answer engine optimisation.",
                    f"HTML CONTENT:\n{cleaned_html}",
                    *image_parts
                ],
                config=genai.types.GenerateContentConfig(
                    tools=[search_tool]
                )
            )

            geo_response = await client.aio.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    "Analyze the following ecommerce product page HTML and screenshots. "
                    "Describe how the product page data could be improved for generative engine optimisation.",
                    f"HTML CONTENT:\n{cleaned_html}",
                    *image_parts
                ],
                config=genai.types.GenerateContentConfig(
                    tools=[search_tool]
                )
            )

            return {
                "desktop_response": desktop_response.text,
                "mobile_response": mobile_response.text
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

# ----------------------------
# LOCAL RUN
# ----------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
