#!/usr/bin/env python3
"""Start the Jarvis Web Server."""

import os
import sys

os.environ.setdefault("JARVIS_TOKEN", "dev-token-change-me")

if __name__ == "__main__":
    import uvicorn
    from jarvis.web.server import app
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"Starting Jarvis Web Server on http://{host}:{port}")
    print(f"Token: {os.environ.get('JARVIS_TOKEN')}")
    print(f"Access at: http://localhost:{port}?token={os.environ.get('JARVIS_TOKEN')}")
    
    uvicorn.run(app, host=host, port=port)