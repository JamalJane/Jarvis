import os
import io
import base64
import asyncio
import logging
import webbrowser
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JARVIS_TOKEN = os.getenv("JARVIS_TOKEN", "dev-token-change-me")

connected_clients: set[WebSocket] = set()

_jarvis_core = None


def get_jarvis_core():
    """Get or create the shared Jarvis core instance."""
    global _jarvis_core
    if _jarvis_core is None:
        from jarvis.core.browser import BrowserController
        from jarvis.core.automation import AutomationController
        from jarvis.config.api_manager import APIManager
        
        home_url = os.getenv("JARVIS_HOME_URL", "https://www.google.com")
        
        _jarvis_core = {
            "api_manager": APIManager(),
            "browser": BrowserController(home_url=home_url),
            "automation": AutomationController()
        }
        logger.info(f"Created Jarvis core with home_url: {home_url}")
    return _jarvis_core


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Jarvis Web Server")
    yield
    logger.info("Shutting down Jarvis Web Server")


app = FastAPI(title="Jarvis Web Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_token(token: str = Query(...)) -> bool:
    if token != JARVIS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid token")
    return True


class CommandRequest(BaseModel):
    action: str
    params: dict = {}


async def broadcast_screenshot(screenshot_b64: str):
    """Send screenshot to all connected WebSocket clients."""
    for client in connected_clients:
        try:
            await client.send_json({
                "type": "screenshot",
                "data": screenshot_b64
            })
        except:
            pass


async def capture_screenshot(browser, automation):
    """Capture screenshot from browser or desktop."""
    screenshot_bytes = None
    
    if browser and browser.is_running():
        try:
            screenshot_bytes = browser.get_screenshot()
        except Exception as e:
            logger.error(f"Browser screenshot failed: {e}")
    
    if not screenshot_bytes and automation:
        try:
            screenshot_bytes = automation.get_screenshot()
        except Exception as e:
            logger.error(f"Desktop screenshot failed: {e}")
    
    if screenshot_bytes:
        return base64.b64encode(screenshot_bytes).decode('utf-8')
    return None


@app.get("/")
async def root(token: str = Depends(verify_token)):
    return HTMLResponse("""
    <html>
        <head>
            <title>Jarvis Control</title>
            <style>
                body { 
                    font-family: Arial, sans-serif; 
                    max-width: 1200px; 
                    margin: 0 auto; 
                    padding: 20px;
                    background: #1a1a2e;
                    color: #eee;
                }
                .container { display: flex; gap: 20px; }
                .screenshot { 
                    flex: 1; 
                    border: 2px solid #16213e;
                    border-radius: 8px;
                    background: #0f0f23;
                }
                .screenshot img { 
                    width: 100%; 
                    display: block;
                    border-radius: 6px;
                }
                .controls { 
                    width: 300px; 
                    background: #16213e;
                    padding: 20px;
                    border-radius: 8px;
                }
                input, button { 
                    width: 100%; 
                    padding: 10px; 
                    margin: 5px 0;
                    border-radius: 4px;
                    border: none;
                }
                input { background: #0f0f23; color: #eee; }
                button { 
                    background: #e94560; 
                    color: white; 
                    cursor: pointer;
                    font-weight: bold;
                }
                button:hover { background: #ff6b6b; }
                .log {
                    margin-top: 20px;
                    padding: 10px;
                    background: #0f0f23;
                    border-radius: 4px;
                    max-height: 200px;
                    overflow-y: auto;
                    font-family: monospace;
                    font-size: 12px;
                }
                h1 { color: #e94560; }
                .status { 
                    padding: 5px 10px; 
                    border-radius: 4px; 
                    margin: 10px 0;
                }
                .connected { background: #2ecc71; }
                .disconnected { background: #e74c3c; }
            </style>
        </head>
        <body>
            <h1>🤖 Jarvis Control Panel</h1>
            <div class="container">
                <div class="screenshot">
                    <img id="screenshot" src="data:image/png;base64," alt="Screen capture">
                </div>
                <div class="controls">
                    <h3>Commands</h3>
                    <input type="text" id="command" placeholder="Enter command...">
                    <button onclick="sendCommand()">Send</button>
                    
                    <h3>Quick Actions</h3>
                    <button onclick="sendCommand('open browser')">Open Browser</button>
                    <button onclick="sendCommand('close browser')">Close Browser</button>
                    <button onclick="refreshScreenshot()">Refresh Screenshot</button>
                    
                    <h3>Status</h3>
                    <div id="status" class="status disconnected">Disconnected</div>
                    
                    <div class="log" id="log"></div>
                </div>
            </div>
            
            <script>
                const ws = new WebSocket(`ws://${window.location.host}/ws?token=${new URLSearchParams(window.location.search).get('token')}`);
                
                ws.onopen = () => {
                    document.getElementById('status').className = 'status connected';
                    document.getElementById('status').textContent = 'Connected';
                    log('Connected to Jarvis');
                };
                
                ws.onmessage = (event) => {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'screenshot') {
                        document.getElementById('screenshot').src = 'data:image/png;base64,' + msg.data;
                    } else if (msg.type === 'response') {
                        log('Jarvis: ' + msg.data);
                    } else if (msg.type === 'error') {
                        log('Error: ' + msg.data);
                    }
                };
                
                ws.onclose = () => {
                    document.getElementById('status').className = 'status disconnected';
                    document.getElementById('status').textContent = 'Disconnected';
                    log('Disconnected');
                };
                
                function sendCommand(cmd) {
                    const input = document.getElementById('command');
                    const command = cmd || input.value;
                    if (!command) return;
                    
                    ws.send(JSON.stringify({ action: 'command', data: command }));
                    log('You: ' + command);
                    input.value = '';
                }
                
                function refreshScreenshot() {
                    ws.send(JSON.stringify({ action: 'screenshot' }));
                    log('Refreshing screenshot...');
                }
                
                function log(msg) {
                    const logDiv = document.getElementById('log');
                    logDiv.innerHTML = '<div>' + msg + '</div>' + logDiv.innerHTML;
                }
                
                document.getElementById('command').addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') sendCommand();
                });
                
                setInterval(refreshScreenshot, 3000);
            </script>
        </body>
    </html>
    """)


@app.get("/screenshot")
async def get_screenshot(token: str = Depends(verify_token)):
    """Get current screenshot."""
    core = get_jarvis_core()
    browser = core.get("browser")
    automation = core.get("automation")
    
    screenshot_b64 = await capture_screenshot(browser, automation)
    
    if not screenshot_b64:
        return JSONResponse({"error": "No screenshot available"}, 500)
    
    return {"screenshot": screenshot_b64}


@app.post("/command")
async def execute_command(
    request: CommandRequest,
    token: str = Depends(verify_token)
):
    """Execute a command on Jarvis."""
    core = get_jarvis_core()
    browser = core.get("browser")
    automation = core.get("automation")
    api_manager = core.get("api_manager")
    
    action = request.action
    params = request.params
    
    result = {"success": True, "message": ""}
    
    try:
        if action == "navigate":
            url = params.get("url", "https://www.google.com")
            if not browser.start():
                raise Exception("Failed to start browser")
            browser.navigate(url)
            result["message"] = f"Navigated to {url}"
            
        elif action == "click":
            x = params.get("x", 0)
            y = params.get("y", 0)
            automation.click(x, y)
            result["message"] = f"Clicked at ({x}, {y})"
            
        elif action == "type":
            text = params.get("text", "")
            automation.type_text(text)
            result["message"] = f"Typed: {text}"
            
        elif action == "press":
            key = params.get("key", "")
            automation.press(key)
            result["message"] = f"Pressed: {key}"
            
        elif action == "scroll":
            clicks = params.get("clicks", 0)
            automation.scroll(clicks)
            result["message"] = f"Scrolled {clicks} clicks"
            
        elif action == "screenshot":
            screenshot_b64 = await capture_screenshot(browser, automation)
            result["screenshot"] = screenshot_b64
            result["message"] = "Screenshot captured"
            
        elif action == "open_browser":
            if not browser.start():
                raise Exception("Failed to start browser")
            result["message"] = "Browser opened"
            
        elif action == "close_browser":
            browser.close()
            result["message"] = "Browser closed"
            
        else:
            result["success"] = False
            result["message"] = f"Unknown action: {action}"
            
    except Exception as e:
        result["success"] = False
        result["message"] = str(e)
        logger.error(f"Command failed: {e}")
    
    return result


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """WebSocket for real-time communication."""
    if token != JARVIS_TOKEN:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    await websocket.accept()
    connected_clients.add(websocket)
    
    try:
        await websocket.send_json({
            "type": "system",
            "message": "Connected to Jarvis"
        })
        
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "command":
                command = data.get("data", "")
                response = await handle_command(command)
                await websocket.send_json({
                    "type": "response",
                    "data": response
                })
                
            elif msg_type == "screenshot":
                core = get_jarvis_core()
                screenshot_b64 = await capture_screenshot(
                    core.get("browser"),
                    core.get("automation")
                )
                if screenshot_b64:
                    await websocket.send_json({
                        "type": "screenshot",
                        "data": screenshot_b64
                    })
                    
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(websocket)


async def handle_command(command: str) -> str:
    """Process a natural language command."""
    core = get_jarvis_core()
    browser = core.get("browser")
    automation = core.get("automation")
    api_manager = core.get("api_manager")
    
    command = command.lower().strip()
    
    try:
        if command.startswith("go to ") or command.startswith("navigate "):
            url = command.replace("go to ", "").replace("navigate ", "").strip()
            if not url.startswith("http"):
                url = "https://" + url
            if not browser.start():
                return "Failed to start browser"
            browser.navigate(url)
            return f"Navigated to {url}"
            
        elif command == "open browser" or command == "start browser":
            if not browser.start():
                return "Failed to start browser"
            return "Browser opened"
            
        elif command == "close browser" or command == "stop browser":
            browser.close()
            return "Browser closed"
            
        elif command == "screenshot" or command == "take screenshot":
            screenshot_b64 = await capture_screenshot(browser, automation)
            if screenshot_b64:
                return "Screenshot captured (sending to client...)"
            return "No screenshot available"
            
        elif command.startswith("type "):
            text = command.replace("type ", "").strip()
            automation.type_text(text)
            return f"Typed: {text}"
            
        elif command.startswith("click "):
            parts = command.replace("click ", "").split()
            if len(parts) >= 2:
                try:
                    x, y = int(parts[0]), int(parts[1])
                    automation.click(x, y)
                    return f"Clicked at ({x}, {y})"
                except:
                    pass
            return "Usage: click <x> <y>"
            
        elif command in ["scroll up", "scroll down"]:
            clicks = -3 if "up" in command else 3
            automation.scroll(clicks)
            return f"Scrolled {'up' if clicks < 0 else 'down'}"
        
        elif command == "desktop screenshot" or command == "screen":
            screenshot_b64 = await capture_screenshot(browser, automation)
            if screenshot_b64:
                return f"Screenshot captured ({len(screenshot_b64)} bytes)"
            return "No screenshot available"
        
        elif command.startswith("open ") and len(command) > 5:
            url = command[5:].strip()
            if url and not url.startswith("http"):
                url = "https://" + url
            if url:
                webbrowser.open(url)
                return f"Opened in your browser: {url}"
            return "Usage: open <url>"
        
        elif command.startswith("open external ") or command.startswith("open system "):
            url = command.replace("open external ", "").replace("open system ", "").strip()
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open(url)
            return f"Opened in your browser: {url}"
        
        elif command.startswith("press "):
            key = command.replace("press ", "").strip()
            automation.press(key)
            return f"Pressed: {key}"
        
        elif command.startswith("hotkey "):
            keys = command.replace("hotkey ", "").split("+")
            automation.hotkey(*keys)
            return f"Hotkey: {'+'.join(keys)}"
        
        elif command == "double click":
            automation.double_click()
            return "Double clicked"
        
        elif command == "right click":
            automation.right_click()
            return "Right clicked"
            
        else:
            return f"Unknown command: {command}. Try: open browser, navigate <url>, type <text>, click <x> <y>, press <key>, hotkey <keys>, scroll up/down, screen, desktop screenshot"
            
    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)