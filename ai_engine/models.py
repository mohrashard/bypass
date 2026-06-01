import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

# Initialize the new Client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY_AUTOPASS"))

print("Available Models:")
for m in client.models.list():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)