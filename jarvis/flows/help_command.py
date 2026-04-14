from jarvis.ui.display import Display


HELP_PANEL = """
╔══════════════════════════════════════════════════════════════════════════╗
║                        JARVIS COMMAND PANEL                               ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  VOICE INPUT                                                            ║
║  ─────────────────────────────────────────────────────────────────────  ║
║  • Press Enter (empty)          → Start voice listening                 ║
║  • Press Enter again            → Stop listening                        ║
║                                                                          ║
║  TEXT COMMANDS                                                          ║
║  ─────────────────────────────────────────────────────────────────────  ║
║  • [any text]                    → Ask a question / give a task           ║
║  • screenshot [question]         → Analyze current screen               ║
║  • type [message]                → Send text without voice              ║
║                                                                          ║
║  BROWSER TASKS                                                           ║
║  ─────────────────────────────────────────────────────────────────────  ║
║  • go to [website]             → Open a website                         ║
║  • search for [query]           → Search on Google                       ║
║  • click [element]              → Click something on page                ║
║  • scroll up/down               → Scroll the page                       ║
║  • extract [data]               → Get info from a page                   ║
║                                                                          ║
║  CONTROL COMMANDS                                                        ║
║  ─────────────────────────────────────────────────────────────────────  ║
║  • open browser                  → Manually open browser                 ║
║  • done / stop                   → End current task                     ║
║  • resume                        → Continue paused task                  ║
║  • /help / help / ?             → Show this help panel                  ║
║                                                                          ║
║  EXAMPLES                                                                ║
║  ─────────────────────────────────────────────────────────────────────  ║
║  • "hello, how are you?"        → Chat with JARVIS                       ║
║  • "search reddit for cats"    → Search Reddit                         ║
║  • "go to github.com"           → Open GitHub                           ║
║  • "extract all prices"         → Scrape data from page                 ║
║  • "what's on my screen?"       → Analyze screenshot                     ║
║                                                                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Press Enter (empty) to use voice input                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""


def show_help():
    print(HELP_PANEL)


def handle_help_command(command: str) -> bool:
    if command.strip().lower() in ["/help", "help", "?"]:
        show_help()
        return True
    return False


def is_help_command(command: str) -> bool:
    return command.strip().lower() in ["/help", "help", "?"]
