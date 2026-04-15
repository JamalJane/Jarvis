"""Self-training configuration constants."""
import os

SIMILARITY_THRESHOLD = float(os.getenv("TRAINING_SIMILARITY_THRESHOLD", "0.85"))
CONFIDENCE_MISMATCH_THRESHOLD = float(os.getenv("TRAINING_MISMATCH_THRESHOLD", "0.30"))
EMBED_DIM = 3072
TRAINING_INDEX_NAME = os.getenv("TRAINING_PINECONE_INDEX", "jarvis-training")
AUTO_REPAIR_ENABLED = os.getenv("TRAINING_AUTO_REPAIR", "true").lower() == "true"
