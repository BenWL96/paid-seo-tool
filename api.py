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


REMOVE_TAGS = [
    # Scripting / execution
    "script", "noscript", "template",

    # Styling / presentation
    "style", "link",

    # SVG / graphics internals
    "svg", "path", "defs", "symbol", "use",

    # Metadata / document structure
    "head", "meta", "base", "title",

    # Layout / chrome (usually non-content)
    "header", "footer", "nav", "aside",

    # Forms / inputs (rarely useful for content analysis)
    "form", "input", "textarea", "select",
    "option", "button", "label", "fieldset", "legend",

    # Media containers you usually don’t want as text
    "canvas", "video", "audio", "source", "track",

    # Embeds / external content
    "iframe", "embed", "object", "param",

    # Tables used for layout (often noise)
    "colgroup", "col", "tbody", "thead", "tfoot",

    # Interactive / disclosure widgets
    "details", "summary", "dialog",

    # Accessibility / annotations (usually redundant)
    "aria-hidden",

    # Rare but noisy
    "map", "area"
]
 
def extract_tagged_text(html):

    soup = BeautifulSoup(html, "html.parser")
    soup = soup.body
    # Remove unwanted elements entirely
    for bad in soup.find_all(REMOVE_TAGS):
        bad.decompose()
    cleaned_html = strip_class_and_id(soup)
    html_no_whitespace = remove_html_whitespace(cleaned_html)
    return html_no_whitespace







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

        # Refine HTML so audit is accurate at a semantic level
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
    cleaned_html = extract_tagged_text(raw_html)
    print(len(cleaned_html))
    exit()
    # soup = BeautifulSoup(raw_html, "html.parser")
    # body = soup.body

    # if not body:
    #     raise ValueError("No <body> tag found")

    # for tag_name in NON_SEO_TAGS:
    #     for tag in body.find_all(tag_name):
    #         tag.decompose()

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
        image_parts = []

        for img_bytes in screenshots:
            image_parts.append(
                genai.types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/png"
                )
            )

        response = await client.aio.models.generate_content(
            model="gemini-3-flash-preview",
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
