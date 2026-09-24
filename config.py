import os
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# PROJECT ROOT
# ============================================================

PROJECT_ROOT = Path(
    __file__
).resolve().parent


# ============================================================
# LOAD .ENV
# ============================================================

ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(
    ENV_FILE
)


# ============================================================
# EMBEDDING CONFIG
# ============================================================

EMBEDDING_PROVIDER = os.getenv(
    "EMBEDDING_PROVIDER"
)

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL"
)

EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL"
)


# ============================================================
# VALIDATION
# ============================================================

if not EMBEDDING_MODEL:
    raise ValueError(
        f"EMBEDDING_MODEL is not set in {ENV_FILE}"
    )

if not EMBEDDING_BASE_URL:
    raise ValueError(
        f"EMBEDDING_BASE_URL is not set in {ENV_FILE}"
    )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("Configuration loaded successfully")
    print("ENV file :", ENV_FILE)
    print("Provider :", EMBEDDING_PROVIDER)
    print("Model    :", EMBEDDING_MODEL)
    print("Base URL :", EMBEDDING_BASE_URL)