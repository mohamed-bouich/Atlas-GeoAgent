"""Agent settings (kept separate so your config.py with your own email is untouched).
Every value can be overridden with an environment variable."""
import os

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")  # keep the model in RAM between questions
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "180"))
REPORT_LANGUAGE = os.getenv("REPORT_LANGUAGE", "en")      # "en" or "fr"
MIN_YEAR = 2019                                            # Sentinel-2 L2A coverage; older years are refused
MAX_REPLANS = 1
