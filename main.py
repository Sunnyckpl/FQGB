from fastapi import FastAPI, HTTPException
from schemas import QuestionRequest, QuestionResponse
import logic_gemini
import logic_openai
import uvicorn

app = FastAPI(title="Nazar QGB API (Dual Model)")

# ---------------------------------------------------------
# ENDPOINT 1: GEMINI 3 FLASH PREVIEW
# URL: POST /generate/gemini
# ---------------------------------------------------------
@app.post("/generate/gemini", response_model=QuestionResponse)
async def route_gemini(request: QuestionRequest):
    try:
        # Calls the Google logic
        result = await logic_gemini.generate_with_gemini(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# ENDPOINT 2: GPT-4o-MINI
# URL: POST /generate/openai
# ---------------------------------------------------------
@app.post("/generate/openai", response_model=QuestionResponse)
async def route_openai(request: QuestionRequest):
    try:
        # Calls the OpenAI logic
        result = await logic_openai.generate_with_openai(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# RUNNER
# ---------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)