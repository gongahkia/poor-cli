import google.generativeai as genai
import os

# Configure with your API key
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("Available models:")
print("-" * 50)
for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f"Model: {model.name}")
        print(f"  Display Name: {model.display_name}")
        print(f"  Supported methods: {model.supported_generation_methods}")
        print()
