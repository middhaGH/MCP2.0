import os, sys
from openai import OpenAI

# Sanity check
print("Python exe:", sys.executable)
import openai as _oa
print("OpenAI version:", _oa.__version__)
print("OpenAI path:", _oa.__file__)

# Instantiate the client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

try:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a career coach."},
            {"role": "user",   "content": "Hi there! How can I improve my resume?"}
        ],
        max_tokens=50
    )
    print("Assistant:", resp.choices[0].message.content.strip())

except Exception as e:
    # This will catch everything, including rate‑limit/quota errors
    print(f"Error ({type(e).__name__}): {e}")
    # Optionally, if it’s a JSON‑style API error you can introspect:
    try:
        err = e.error if hasattr(e, "error") else None
        print("Error details:", err)
    except:
        pass
