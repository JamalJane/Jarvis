import os
import sys
from dotenv import load_dotenv

# Try to load .env
try:
    load_dotenv()
    api_key = os.getenv("PINECONE_API_KEY")
    print(f"API Key found: {'Yes' if api_key else 'No'} (starts with {api_key[:10] if api_key else 'None'})")
    
    from pinecone import Pinecone
    pc = Pinecone(api_key=api_key)
    print("Pinecone client initialized.")
    indexes = pc.list_indexes().names()
    print(f"Indexes on Pinecone: {list(indexes)}")
except Exception as e:
    print(f"ERROR: {e}")
