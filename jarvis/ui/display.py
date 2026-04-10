import sys
try:
    from rich.console import Console
    from rich.theme import Theme
    _theme = Theme({
        "info": "dim cyan",
        "warning": "magenta",
        "danger": "bold red",
        "success": "bold green",
        "jarvis": "bold blue"
    })
    console = Console(theme=_theme)
except ImportError:
    console = None

class Display:
    @classmethod
    def _emit(cls, message: str, msg_type: str = "status"):
        if console:
            if msg_type == "error":
                console.print(f"❌ [danger]{message}[/danger]")
            elif msg_type == "success":
                console.print(f"✅ [success]{message}[/success]")
            elif msg_type == "warning":
                console.print(f"⚠️ [warning]{message}[/warning]")
            elif msg_type == "bot":
                from rich.markdown import Markdown
                console.print("\n[jarvis]🤖 Jarvis:[/jarvis]")
                console.print(Markdown(message))
                console.print("")
            elif msg_type == "user":
                console.print(f"[bold cyan]❯ You:[/bold cyan] {message}")
            else:
                console.print(f"ℹ️ [info]{message}[/info]")
        else:
            # Fallback to CLI
            if msg_type == "error":
                print(f"[ERROR] {message}", file=sys.stderr)
            elif msg_type == "success":
                print(f"[✓] {message}")
            elif msg_type == "warning":
                print(f"[⚠] {message}")
            elif msg_type == "bot":
                print(f"Jarvis: {message}")
            elif msg_type == "user":
                print(f"You: {message}")
            else:
                print(f"[STATUS] {message}")

    @staticmethod
    def greeting(username: str, summary: str = ""):
        msg = f"Hello {username} 👋"
        if summary:
            msg += f"\n{summary}"
        Display._emit(msg, "bot")

    @staticmethod
    def prompt():
        Display._emit("What do you need?", "bot")

    @staticmethod
    def status(message: str):
        Display._emit(message, "status")

    @staticmethod
    def error(message: str):
        Display._emit(message, "error")

    @staticmethod
    def success(message: str):
        Display._emit(message, "success")

    @staticmethod
    def warning(message: str):
        Display._emit(message, "warning")

