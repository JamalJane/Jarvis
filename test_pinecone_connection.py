"""Quick test to verify .env loads and Pinecone connects."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

api_key = os.getenv("PINECONE_API_KEY")
print(f"[1] PINECONE_API_KEY loaded: {bool(api_key)}")
if api_key:
    print(f"    Key prefix: {api_key[:12]}...")

if not api_key:
    print("ERROR: PINECONE_API_KEY not found in .env")
    exit(1)

# Try to import and connect
try:
    from pinecone import Pinecone
    print("[2] Pinecone SDK imported successfully")

    pc = Pinecone(api_key=api_key)
    print("[3] Pinecone client created successfully")

    # List existing indexes to confirm auth works
    indexes = pc.list_indexes()
    index_names = [idx.name for idx in indexes]
    print(f"[4] Connected! Existing indexes: {index_names if index_names else '(none yet)'}")

    # Verify PineconeStore integration
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from jarvis.memory.pinecone_store import PineconeStore
    store = PineconeStore(api_key=api_key)
    store._ensure_initialized()
    stats = store.get_stats()
    print(f"[5] PineconeStore connected: {stats['pinecone_connected']} | vectors stored: {stats['total_stored']}")

except ImportError:
    print("ERROR: pinecone package not installed. Run: pip install pinecone>=3.0.0")
except Exception as e:
    print(f"ERROR connecting to Pinecone: {e}")
