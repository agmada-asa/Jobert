import google.generativeai as genai
import httpx
import io
import PyPDF2
from typing import List, Dict
from .encryption import decrypt_string
from .notion_api import get_kb_content

async def extract_pdf_text(url: str) -> str:
    """Downloads a PDF from a URL and extracts its text."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        if response.status_code != 200:
            return ""
        
        pdf_file = io.BytesIO(response.content)
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

async def generate_tailored_answers(
    user_data: dict, 
    job_url: str, 
    questions: List[Dict[str, str]]
) -> Dict[str, str]:
    """
    Uses Gemini to generate tailored answers based on user's CV and Notion KB.
    """
    # 1. Decrypt keys
    gemini_key = decrypt_string(user_data.get("gemini_api_key"))
    notion_token = decrypt_string(user_data.get("notion_token"))
    
    if not gemini_key:
        raise Exception("Gemini API key not found for user.")

    # 2. Gather User Context
    cv_text = ""
    if user_data.get("cv_url"):
        cv_text = await extract_pdf_text(user_data["cv_url"])
    
    kb_text = ""
    if user_data.get("notion_kb_page_id") and notion_token:
        kb_text = await get_kb_content(notion_token, user_data["notion_kb_page_id"])

    # 3. Configure Gemini
    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel('gemini-1.5-flash')

    # 4. Construct Prompt
    # We include instructions to be concise and stick to the user's data.
    prompt = f"""
    You are an expert job application assistant. Your goal is to answer specific form questions 
    for a job application at the following URL: {job_url}

    USER BACKGROUND (from CV):
    {cv_text}

    USER PREFERENCES & ADDITIONAL INFO (from Knowledge Base):
    {kb_text}

    QUESTIONS TO ANSWER:
    {questions}

    INSTRUCTIONS:
    1. Answer every question listed above based ONLY on the provided user context.
    2. If a question asks for contact info (email, phone, LinkedIn), use the exact values from the CV.
    3. For open-ended questions (e.g., "Why do you want to work here?"), use the Knowledge Base and CV to tailor the answer to the job.
    4. Keep answers professional, concise, and ready to be pasted into a form.
    5. RETURN THE ANSWERS IN A JSON FORMAT where the key is the "id" provided in the QUESTIONS list and the value is your generated answer.
    
    Format:
    {{
      "id_1": "answer_1",
      "id_2": "answer_2"
    }}
    """

    # 5. Call LLM
    response = model.generate_content(prompt)
    
    try:
        # Clean response if it contains markdown code blocks
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
        
        import json
        return json.loads(text)
    except Exception as e:
        print(f"Failed to parse Gemini response: {e}\nRaw response: {response.text}")
        # Fallback to simple logic if JSON parsing fails
        return {q["id"]: "Error generating answer" for q in questions}
