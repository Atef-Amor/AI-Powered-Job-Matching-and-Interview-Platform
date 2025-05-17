import os
import openai
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_base = "https://openrouter.ai/api/v1"

def call_openai(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt}
            ],
            headers={
                "HTTP-Referer": os.getenv("HTTP_REFERER", ""),
                "X-Title": os.getenv("APP_TITLE", "InterviewBot"),
            }
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        return f"Error: {str(e)}"