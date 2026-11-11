import os
from dotenv import load_dotenv

load_dotenv()

def get_llm(temperature: float = 0.0):
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    api_key = os.getenv("LLM_API_KEY")

    if not api_key:
        raise ValueError("Missing LLM_API_KEY in environment variables.")

    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, api_key=api_key, temperature=temperature)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, api_key=api_key, temperature=temperature)
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")