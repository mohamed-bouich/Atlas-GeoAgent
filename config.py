"""Central configuration.

Every value can be overridden with an environment variable, so the same code
runs on your laptop, in Docker, or in CI without editing files.
"""

import os
from pathlib import Path

ROOT_DIR= Path(__file__).resolve().parent
DATA_DIR=ROOT_DIR/ "data"
CACHE_DIR = DATA_DIR /"cache"
LOGS_DIR=ROOT_DIR/ "logs"

# Sentinel-2 L2A through the free Earth Search STAC API
STAC_URL = os.getenv("STAC_URL", "https://earth-search.aws.element84.com/v1")
STAC_COLLECTION = os.getenv("STAC_COLLECTION", "sentinel-2-l2a")
MAX_CLOUD_COVER = float(os.getenv("MAX_CLOUD_COVER", "20"))  # percent

# Geocoding (Nominatim). Their policy requires an identifying User-Agent.
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = os.getenv(
    "USER_AGENT", "geo-agent-student-project/0.1 (contact: YOUR EMAIL.com)"
)

# Safety limits: protect your laptop and the public APIs
MAX_AOI_KM2 = float(os.getenv("MAX_AOI_KM2", "400"))
DEFAULT_HALF_SIZE_KM = float(os.getenv("DEFAULT_HALF_SIZE_KM", "5"))

# Local LLM (used from step 5)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")


def ensure_dirs() -> None:
    """Create runtime folders. Called by entry points, not at import time."""
    for folder in (CACHE_DIR, LOGS_DIR):
        folder.mkdir(parents=True, exist_ok=True)
