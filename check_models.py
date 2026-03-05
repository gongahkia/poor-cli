from google import genai
import os

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("Available models:")
print("-" * 50)
for model in client.models.list():
    if hasattr(model, "supported_generation_methods") and 'generateContent' in (model.supported_generation_methods or []):
        print(f"Model: {model.name}")
        print(f"  Display Name: {model.display_name}")
        print(f"  Supported methods: {model.supported_generation_methods}")
        print()
