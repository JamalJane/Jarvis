from jarvis.memory.pinecone_store import PineconeStore

store = PineconeStore()
print(f"Stats: {store.get_stats()}")
print(f"API key loaded: {store.api_key[:10]}..." if store.api_key else "No API key")
print(f"Index: {store.index}")