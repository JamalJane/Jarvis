import logging
import sys
import os
from pathlib import Path
from jarvis.config.api_manager import APIManager
from jarvis.core.voice import VoiceIO
from jarvis.core.browser import BrowserController
from jarvis.core.automation import AutomationController
from jarvis.core.task_manager import TaskManager
from jarvis.flows.startup import run_startup
from jarvis.flows.voice_query import run_voice_query
from jarvis.flows.blacklist_action import BlacklistHandler
from jarvis.flows.resume_task import ResumeHandler
from jarvis.flows.help_command import handle_help_command
from jarvis.memory.pinecone_store import PineconeStore
from jarvis.memory.prediction import PredictionEngine
from jarvis.memory.context_selector import ContextSelector
from jarvis.memory.context_guard import ContextGuard
from jarvis.memory.local_store import LocalMemoryStore
from jarvis.ui.display import Display

logger = logging.getLogger(__name__)

# ANSI colors for REPL command output
_G   = "\033[32m"
_Y   = "\033[33m"
_R   = "\033[31m"
_DIM = "\033[2m"
_RST = "\033[0m"
_B   = "\033[1m"


class Jarvis:
    def __init__(self):
        self.api_manager = APIManager()
        self.voice = VoiceIO()
        self.browser = BrowserController()
        self.automation = AutomationController()
        self.blacklist_handler = BlacklistHandler()
        self.resume_handler = ResumeHandler()

        pinecone_key = os.getenv("PINECONE_API_KEY", "")
        pinecone = PineconeStore(api_key=pinecone_key)
        self.prediction_engine = PredictionEngine(pinecone)
        self.context_selector = ContextSelector(self.prediction_engine)

        self.task_manager = TaskManager(
            api_manager=self.api_manager,
            browser=self.browser,
            automation=self.automation,
            pinecone_store=pinecone
        )

        # Context overflow protection
        self.context_guard = ContextGuard()

        # Local hybrid memory (TF-IDF + vector + MMR)
        self.local_memory = LocalMemoryStore()

        # In-session conversation history for context tracking
        self._conversation: list[dict] = []

    # ------------------------------------------------------------------ #
    # BOOT                                                                  #
    # ------------------------------------------------------------------ #

    def run(self):
        username = run_startup(self.api_manager)
        if self.resume_handler.check_for_paused_task():
            Display.status("Found paused task. Type 'resume' to continue.")

        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.formatted_text import HTML
            from prompt_toolkit.history import InMemoryHistory
            from prompt_toolkit.styles import Style

            style = Style.from_dict({'prompt': '#00ffff bold'})
            session = PromptSession(history=InMemoryHistory())

            while True:
                user_input = session.prompt(
                    HTML('<prompt>❯ You: </prompt>'),
                    style=style
                ).strip()

                if not user_input:
                    continue

                if user_input.lower() in ["exit", "quit", "done"]:
                    break

                # REPL slash commands — handled before AI dispatch
                if user_input.startswith("/"):
                    if self._handle_repl_command(user_input):
                        continue

                self.process_command(user_input)

        except (KeyboardInterrupt, EOFError):
            Display.status("Shutting down gracefully...")
        finally:
            self.cleanup()

    # ------------------------------------------------------------------ #
    # REPL COMMANDS                                                         #
    # ------------------------------------------------------------------ #

    def _handle_repl_command(self, cmd: str) -> bool:
        """Handle /slash commands. Returns True if command was consumed."""
        parts = cmd.strip().split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if command == "/context":
            report = self.context_guard.usage_report(self._conversation)
            pct    = report["percent"]
            bar_n  = 30
            filled = int(bar_n * min(pct, 100) / 100)
            bar    = "#" * filled + "-" * (bar_n - filled)
            color  = _G if pct < 50 else (_Y if pct < 80 else _R)
            print(f"\n  Context window usage:")
            print(f"  {color}[{bar}] {pct}%{_RST}")
            print(f"  ~{report['estimated_tokens']:,} / {report['limit']:,} tokens")
            print(f"  {report['message_count']} messages in session\n")
            return True

        if command == "/compact":
            if len(self._conversation) <= 4:
                print(f"{_DIM}  Too few messages to compact (need > 4).{_RST}")
                return True
            before = len(self._conversation)
            self._conversation = self.context_guard.compact_history(
                self._conversation, self.api_manager
            )
            after = len(self._conversation)
            print(f"{_G}  Compacted: {before} → {after} messages{_RST}")
            return True

        if command == "/memory":
            stats = self.local_memory.get_stats()
            print(f"\n  Local memory:")
            print(f"  Evergreen (MEMORY.md): {stats['evergreen_chars']} chars")
            print(f"  Daily files: {stats['daily_files']}")
            print(f"  Daily entries: {stats['daily_entries']}\n")
            return True

        if command == "/search":
            if not arg:
                print(f"{_Y}  Usage: /search <query>{_RST}")
                return True
            results = self.local_memory.search(arg)
            if not results:
                print(f"{_DIM}  No results.{_RST}")
            else:
                print(f"\n  Memory search: '{arg}'")
                for r in results:
                    color = _G if r["score"] > 0.3 else _DIM
                    print(f"  {color}[{r['score']:.3f}]{_RST} {r['path']}")
                    print(f"    {_DIM}{r['snippet']}{_RST}")
                print()
            return True

        if command == "/remember":
            if not arg:
                print(f"{_Y}  Usage: /remember <fact>{_RST}")
                return True
            result = self.local_memory.write_memory(arg, category="manual")
            print(f"{_G}  {result}{_RST}")
            return True

        if command == "/help":
            print(f"""
{_B}  Jarvis REPL Commands:{_RST}
  /context          Show context window usage
  /compact          Summarize + compress conversation history
  /memory           Show local memory stats
  /search <q>       Hybrid-search stored memories
  /remember <fact>  Save a fact to local memory
  /help             Show this help
  exit / quit       Shut down
""")
            return True

        return False   # unknown slash command — let AI handle it

    # ------------------------------------------------------------------ #
    # COMMAND DISPATCH                                                       #
    # ------------------------------------------------------------------ #

    def process_command(self, user_input: str):
        if not user_input:
            user_input = self._handle_voice_input()
            if not user_input:
                return

        if handle_help_command(user_input):
            return

        if user_input.lower() == "resume":
            state = self.resume_handler.resume_task()
            if state:
                self._execute_resumed_task(state)
            return

        if user_input.lower() == "open browser":
            self._open_browser()
            return

        if user_input.lower() in ["done", "stop"]:
            Display.status("Task ended")
            return

        query = user_input[5:] if user_input.startswith("type ") else user_input
        if query:
            self._execute_query(query)

    def _handle_voice_input(self) -> str:
        Display.status("Voice mode active")
        return run_voice_query()

    def _needs_browser(self, query: str) -> bool:
        query_lower = query.lower()
        # Only open browser when explicitly told to or URL is provided
        explicit_browser = [
            "open browser", "open the browser", "start browser", "launch browser",
            "go to ", "goto ", "navigate to", "visit ", "browse to ",
            "http://", "https://", ".com", ".org", ".io", ".net",
        ]
        return any(keyword in query_lower for keyword in explicit_browser)

    def _open_browser(self):
        if not self.browser.is_running():
            if not self.browser.start():
                Display.error("Failed to start browser")
                return
        Display.success("Browser opened")
        home_url = os.getenv("JARVIS_HOME_URL", "https://www.google.com")
        self.browser.navigate(home_url)

    def _execute_query(self, query: str):
        Display.status(f"Processing: {query}")

        # Auto-recall relevant memories before sending to AI
        recalled = self.local_memory.search(query, top_k=3)
        if recalled:
            memory_ctx = "\n".join(
                f"- [{r['path']}] {r['snippet']}" for r in recalled
            )
            query = f"{query}\n\n[Recalled memory context]\n{memory_ctx}"

        # Track in conversation history
        self._conversation.append({"role": "user", "content": query})

        if self._needs_browser(query):
            if not self.browser.is_running():
                Display.status("Opening browser...")
                if not self.browser.start():
                    Display.error("Failed to start browser")
                    return
        else:
            result = self._process_non_browser_query(query)
            if result:
                return

        try:
            result = self.task_manager.execute_task(query)
            if result.success:
                Display.success(f"Task completed: {result.actions_completed} actions")
            else:
                Display.error(f"Task failed: {result.error}")
        except Exception as e:
            logger.error(f"Task failed: {e}")
            Display.error(f"Task failed: {e}")

    def _process_non_browser_query(self, query: str):
        try:
            Display.status("Sending to AI...")
            response = self.context_guard.guard_call(
                api_manager=self.api_manager,
                prompt=query,
                screenshot_b64=None,
                messages=self._conversation,
            )
            self._conversation.append({"role": "assistant", "content": response})
            Display.success(response)
            return True
        except Exception as e:
            logger.error(f"Query failed: {e}")
            Display.error(f"Query failed: {e}")
            return False

    def _execute_resumed_task(self, state):
        logger.info(f"Resuming task: {state.task_name}")
        Display.status(f"Resuming: {state.task_name}")
        self._execute_query(state.task_name)

    def cleanup(self):
        if self.browser:
            self.browser.close()
        Display.status("JARVIS shutting down...")


def main():
    jarvis = Jarvis()
    jarvis.run()


if __name__ == "__main__":
    main()
