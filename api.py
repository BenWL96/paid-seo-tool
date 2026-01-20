import os
from fastapi import FastAPI, HTTPException
from google import genai
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Initialize the client. The SDK handles async pooling efficiently.
client = genai.Client(
    vertexai=False,
    api_key=os.environ.get("GOOGLE_API_KEY")
)


@app.get("/ask")
async def ask_gemini():
    try:
        # Use the standard generate_content call within an async function
        # The SDK is built to be non-blocking in async contexts
        response = await client.models.generate_content(
            model="gemini-2.0-flash",
            contents="explain quantum physics in 20 words"
        )
        print("success")

        return {"response": response.text}

    except Exception as e:
        print("failure")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

