# JARVIS - Autonomous AI Assistant

An intelligent desktop automation agent with voice I/O, screen automation, and predictive learning powered by Gemini API with Pinecone vector storage.

## Features

- **Voice I/O**: Natural voice commands via Google STT + pyttsx3
- **Screen Automation**: Web automation via Selenium, OS automation via pyautogui
- **4-Key Gemini Fallback**: Redundant API keys with automatic failover
- **Predictive Learning**: Pinecone vector storage learns from actions
- **Task Resume**: Pause and resume tasks seamlessly
- **Safety**: Blacklist system for dangerous actions with user approval
- **Hotkey Activation**: Global hotkey (Ctrl+Alt+J) to launch from anywhere

## Quick Start

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API keys** in `.env`:
   ```env
   GEMINI_KEY_1=your_key_here
   GEMINI_KEY_2=your_key_here
   GEMINI_KEY_3=your_key_here
   GEMINI_KEY_4=your_key_here
   PINECONE_API_KEY=your_key_here
   ```

3. **Configure Google Cloud credentials** (for Gmail, Calendar, Drive access):
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Create a project and enable APIs: Gmail API, Google Calendar API, Google Drive API, Google Docs API
   - Create OAuth 2.0 credentials (Desktop application)
   - Download the credentials file as `credentials.json`
   - On first run, the app will prompt you to authorize via browser login

3. **Run tests**:
   ```bash
   python -c "import pytest; pytest.main()"
   ```

4. **Start JARVIS**:
   ```bash
   python jarvis.py
   ```

5. **Start hotkey daemon** (optional - enables global hotkey):
   ```bash
   python -m jarvis.daemon
   ```
   Then press `Ctrl+Alt+J` to launch JARVIS from anywhere

## Commands

| Command | Description |
|---------|-------------|
| Press Enter | Start voice listening |
| Press Enter again | Stop voice listening |
| Type text | Direct text query |
| `screenshot [prompt]` | Screenshot analysis |
| `done` / `stop` | End current task |
| `resume` | Continue paused task |
| `/help` | Show help |

## Architecture

```
jarvis/
├── jarvis.py              # Main entry point
├── daemon.py              # Hotkey daemon
├── config/                # Configuration
│   ├── api_manager.py     # 4-key Gemini fallback
│   ├── blacklist.py      # Blacklisted actions
│   └── constants.py       # Settings
├── core/                  # Core functionality
│   ├── voice.py           # STT + TTS
│   ├── screenshot.py      # Screen capture
│   ├── browser.py         # Selenium wrapper
│   ├── automation.py      # pyautogui actions
│   └── task_manager.py    # Task execution
├── memory/                # Learning system
│   ├── pinecone_store.py  # Vector storage
│   ├── prediction.py      # ML predictions
│   └── context_selector.py # Hybrid → Predictive
├── flows/                 # User flows
│   ├── startup.py         # Flow 1
│   ├── voice_query.py     # Flow 2
│   ├── retry_logic.py     # Flow 4
│   ├── blacklist_action.py # Flow 5
│   ├── resume_task.py    # Flow 6
│   └── help_command.py    # Flow 7
└── ui/
    └── display.py         # Terminal display
```

## License

MIT
