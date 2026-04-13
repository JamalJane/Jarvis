import logging
import sys
import os
import time
from pathlib import Path
from jarvis.config.api_manager import APIManager
from jarvis.core.voice import VoiceIO
from jarvis.core.browser import BrowserController
from jarvis.core.automation import AutomationController
from jarvis.core.task_manager import TaskManager
from jarvis.core.google_services import GoogleServices
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
from jarvis.self_improvement.agent import SelfImprovementAgent
from jarvis.self_improvement.session_lock import SessionLock

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
        self._pinecone = pinecone
        self.prediction_engine = PredictionEngine(pinecone)
        self.context_selector = ContextSelector(self.prediction_engine)

        # Google APIs — Gmail, Calendar, Docs
        # Auth runs once at startup; token cached in GOOGLE_TOKEN_PATH (.env)
        self.google_services = GoogleServices()
        if self.google_services.is_authenticated():
            Display.status("Google APIs authenticated (Gmail, Calendar, Docs ready)")
        else:
            logger.warning("Google APIs unavailable — check credentials or network")

        self.task_manager = TaskManager(
            api_manager=self.api_manager,
            browser=self.browser,
            automation=self.automation,
            pinecone_store=pinecone,
            google_services=self.google_services,
        )

        # Context overflow protection
        self.context_guard = ContextGuard()

        # Local hybrid memory (TF-IDF + vector + MMR)
        self.local_memory = LocalMemoryStore()

        # In-session conversation history for context tracking
        self._conversation: list[dict] = []

        # Self-improvement agent (Step 28)
        self.self_improvement = SelfImprovementAgent()
        self._si_lock = SessionLock()

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

        if command == "/optimize":
            print(f"\n{_Y}  Starting self-improvement session...{_RST}")
            self.self_improvement.run_session(
                self.task_manager.get_history(), self.api_manager, self._pinecone
            )
            return True

        if command == "/analyze":
            print(f"\n{_Y}  Analysing codebase (no changes applied)...{_RST}")
            self.self_improvement.run_analysis_only(
                self.task_manager.get_history(), self.api_manager
            )
            return True

        if command == "/improvements":
            self.self_improvement.show_history()
            return True

        if command == "/revert":
            print(f"\n{_Y}  Reverting last self-improvement commit...{_RST}")
            ok = self.self_improvement.rollback_last_commit()
            if ok:
                print(f"  {_G}✓ Rollback complete.{_RST}")
            else:
                print(f"  {_R}✗ Rollback failed — see instructions above.{_RST}")
            return True

        if command == "/improvements-off":
            self.self_improvement.disable_auto()
            print(f"  {_Y}Auto self-improvement disabled.{_RST}")
            return True

        if command == "/improvements-on":
            self.self_improvement.enable_auto()
            print(f"  {_G}Auto self-improvement enabled.{_RST}")
            return True

        if command == "/help":
            print(f"""
{_B}  Jarvis REPL Commands:{_RST}
  /context              Show context window usage
  /compact              Summarize + compress conversation history
  /memory               Show local memory stats
  /search <q>           Hybrid-search stored memories
  /remember <fact>      Save a fact to local memory

{_B}  Self-Improvement:{_RST}
  /optimize             Run full self-improvement session (reads code, applies fixes, commits)
  /analyze              Analyse codebase only — no files changed, no git
  /improvements         Show self-improvement history dashboard
  /revert               Undo last self-improvement commit (git revert HEAD)
  /improvements-off     Disable future auto-improvement sessions
  /improvements-on      Re-enable auto-improvement sessions

  /help                 Show this help
  exit / quit           Shut down
""")
            return True

        return False   # unknown slash command — let AI handle it

    # ------------------------------------------------------------------ #
    # COMMAND DISPATCH                                                       #
    # ------------------------------------------------------------------ #

    # Natural language self-improvement triggers
    _NL_OPTIMIZE = [
        "optimize yourself", "improve your code", "self optimize",
        "self-optimize", "improve yourself",
    ]
    _NL_ANALYZE = [
        "check for issues", "analyze yourself", "analyse yourself",
        "find bugs in yourself",
    ]

    def process_command(self, user_input: str):
        if not user_input:
            user_input = self._handle_voice_input()
            if not user_input:
                return

        if handle_help_command(user_input):
            return

        # Natural language self-improvement triggers
        lower = user_input.lower()
        for phrase in self._NL_OPTIMIZE:
            if phrase in lower:
                print(f"\n{_Y}  Triggering self-improvement session...{_RST}")
                self.self_improvement.run_session(
                    self.task_manager.get_history(), self.api_manager, self._pinecone
                )
                return
        for phrase in self._NL_ANALYZE:
            if phrase in lower:
                self.self_improvement.run_analysis_only(
                    self.task_manager.get_history(), self.api_manager
                )
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

        if self._handle_simple_query(user_input):
            return

        query = user_input[5:] if user_input.startswith("type ") else user_input
        if query:
            self._execute_query(query)

    def _handle_simple_query(self, user_input: str) -> bool:
        """Handle simple conversational queries directly without API calls. Returns True if handled."""
        lower = user_input.lower().strip()
        
        for prefix in ["jarvis ", "hey "]:
            if lower.startswith(prefix):
                lower = lower[len(prefix):]
        
        greetings = ["how are we", "how are you", "how r we", "how r you", "hows it going", "wassup", "what's up", ""]
        if lower in greetings or not lower:
            print(f"\n{_G}  All good! Ready when you are.{_RST}\n")
            return True

        simple_status = ["status", "ping", "are you there"]
        if lower in simple_status:
            print(f"\n{_G}  Online and ready.{_RST}\n")
            return True

        thanks = ["thanks", "thank you", "thx", "ty"]
        if lower in thanks:
            print(f"\n{_G}  You're welcome!{_RST}\n")
            return True

        okay = ["ok", "okay", "k", "kk", "roger"]
        if lower in okay:
            return True

        return False

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

    # ── Google-intent keyword sets (broad single-word triggers) ───────────────
    # ANY mention of these words routes to Google APIs — no need for exact phrases
    _GOOGLE_EMAIL_KW = ["email", "gmail", "inbox", "mail"]
    _GOOGLE_CALENDAR_KW = ["calendar", "schedule", "meeting", "event", "appointment"]
    _GOOGLE_DOCS_KW = ["doc", "document", "gdoc", "google doc"]

    # Words that indicate "read/check" vs "send/write" for email
    _EMAIL_READ_KW = [
        "check", "read", "show", "list", "what", "recent",
        "unread", "inbox", "latest", "get", "fetch", "look",
    ]
    _EMAIL_SEND_KW = [
        "send", "write", "compose", "draft", "reply", "forward",
        "email to", "mail to", "message to",
        "saying", "tell ", "let them know", "notify", "let him know", "let her know",
    ]

    def _classify_google_intent(self, query: str) -> str:
        """Returns 'email', 'calendar', 'doc', or '' if not a Google task."""
        if not (self.google_services and self.google_services.is_authenticated()):
            return ""
        q = query.lower()
        if any(kw in q for kw in self._GOOGLE_EMAIL_KW):
            return "email"
        if any(kw in q for kw in self._GOOGLE_CALENDAR_KW):
            return "calendar"
        if any(kw in q for kw in self._GOOGLE_DOCS_KW):
            return "doc"
        return ""

    def _email_sub_intent(self, query: str) -> str:
        """Returns 'send' or 'read' based on action words in the query."""
        q = query.lower()
        # If there's a clear send signal, prefer send
        if any(kw in q for kw in self._EMAIL_SEND_KW):
            return "send"
        # Otherwise default to reading
        return "read"

    def _handle_google_task(self, intent: str, query: str):
        """
        Handle a Google API task deterministically.
        Uses the LLM ONLY to extract structured params from natural language,
        then calls google_services directly — the action loop is never entered.
        """
        import json as _json

        if intent == "email":
            sub = self._email_sub_intent(query)

            if sub == "send":
                Display.status("Extracting email details...")
                extraction_prompt = (
                    f"Extract the email details from this request. Respond with ONLY valid JSON.\n"
                    f"Request: {query}\n"
                    f'JSON format: {{"to": "email@address.com", "subject": "subject line", "body": "email body"}}\n'
                    f"If no email address is mentioned for 'to', use an empty string."
                )
                raw = self.api_manager.call_api(extraction_prompt)
                try:
                    start = raw.find('{')
                    end   = raw.rfind('}') + 1
                    params = _json.loads(raw[start:end])
                    to      = params.get("to", "").strip()
                    subject = params.get("subject", "No Subject").strip()
                    body    = params.get("body", "").strip()
                    if not to or "@" not in to:
                        Display.error(
                            f"Couldn't find a valid recipient address.\n"
                            f"Parsed: to='{to}' subject='{subject}'\n"
                            f"Try: 'send an email to someone@gmail.com saying ...'"
                        )
                        return
                    # Confirmation before sending
                    print(f"\n  To:      {to}")
                    print(f"  Subject: {subject}")
                    print(f"  Body:    {body[:80]}{'...' if len(body) > 80 else ''}\n")
                    result = self.google_services.send_email(to, subject, body)
                    msg_id = result.get("id", "?")
                    Display.success(f"Email sent to {to} (Gmail ID: {msg_id})")
                except Exception as e:
                    logger.error(f"Email send failed: {e}")
                    Display.error(f"Failed to send email: {e}")

            else:  # read / check inbox
                Display.status("Fetching recent emails...")
                # Let LLM extract an optional Gmail search filter
                extraction_prompt = (
                    f"Extract a Gmail search filter from this request if any. "
                    f"Respond with ONLY valid JSON.\n"
                    f"Request: {query}\n"
                    f'JSON format: {{"query": "gmail search string or empty string", "max_results": 10}}\n'
                    f"Gmail search examples: 'is:unread', 'from:boss@co.com', 'subject:invoice'"
                )
                raw = self.api_manager.call_api(extraction_prompt)
                gmail_query = ""
                max_results = 10
                try:
                    start = raw.find('{')
                    end   = raw.rfind('}') + 1
                    params = _json.loads(raw[start:end])
                    gmail_query = params.get("query", "").strip()
                    max_results = int(params.get("max_results", 10))
                except Exception:
                    pass  # use defaults

                try:
                    emails = self.google_services.list_recent_emails(
                        max_results=max_results, query=gmail_query
                    )
                    if not emails:
                        Display.success("No emails found matching that search.")
                    else:
                        lines = []
                        for e in emails:
                            lines.append(
                                f"  From:    {e['from']}\n"
                                f"  Subject: {e['subject']}\n"
                                f"  Preview: {e['snippet'][:100]}\n"
                            )
                        Display.success(
                            f"Found {len(emails)} email(s)"
                            + (f" matching '{gmail_query}'" if gmail_query else "") + ":\n\n"
                            + "\n---\n".join(lines)
                        )
                except Exception as e:
                    logger.error(f"Email list failed: {e}")
                    Display.error(f"Failed to fetch emails: {e}")

        elif intent == "calendar":
            Display.status("Fetching your calendar...")
            try:
                events = self.google_services.list_upcoming_events(max_results=10)
                if not events:
                    Display.success("No upcoming events found on your Google Calendar.")
                else:
                    lines = []
                    for ev in events:
                        start = ev['start'].get('dateTime', ev['start'].get('date'))
                        lines.append(f"  {start}: {ev.get('summary', '(no title)')}")
                    Display.success("Upcoming events:\n" + "\n".join(lines))
            except Exception as e:
                logger.error(f"Calendar fetch failed: {e}")
                Display.error(f"Calendar error: {e}")

        elif intent == "doc":
            Display.status("Extracting document title...")
            extraction_prompt = (
                f"Extract the document title from this request. Respond with ONLY valid JSON.\n"
                f"Request: {query}\n"
                f'JSON format: {{"title": "document title here"}}\n'
                f"If no clear title is mentioned, use 'Untitled Document'."
            )
            raw = self.api_manager.call_api(extraction_prompt)
            try:
                start = raw.find('{')
                end   = raw.rfind('}') + 1
                params = _json.loads(raw[start:end])
                title = params.get("title", "Untitled Document").strip()
                Display.status(f"Creating Google Doc: '{title}'...")
                doc = self.google_services.create_doc(title)
                doc_id  = doc.get('documentId')
                doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
                Display.success(f"Created: '{title}'\n   {doc_url}")
            except Exception as e:
                logger.error(f"Doc creation failed: {e}")
                Display.error(f"Failed to create doc: {e}")



    def _open_browser(self):
        if not self.browser.is_running():
            if not self.browser.start():
                Display.error("Failed to start browser")
                return
        Display.success("Browser opened")
        home_url = os.getenv("JARVIS_HOME_URL", "https://www.google.com")
        self.browser.navigate(home_url)

    def _execute_query(self, query: str):
        # Concurrency guard: wait if self-improvement is patching files
        if self._si_lock.is_active():
            Display.status("Self-improvement is running — waiting up to 5 min...")
            deadline = time.time() + 300
            while self._si_lock.is_active() and time.time() < deadline:
                time.sleep(2)
            if self._si_lock.is_active():
                Display.status("Proceeding anyway (self-improvement still running).")

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

        # Google API tasks — handled deterministically, never via desktop automation
        google_intent = self._classify_google_intent(query)
        if google_intent:
            self._handle_google_task(google_intent, query)
            return

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
            messages_with_query = self._conversation + [{"role": "user", "content": f"Question: {query}\nAnswer directly without any actions."}]
            response = self.context_guard.guard_call(
                api_manager=self.api_manager,
                prompt="",
                screenshot_b64=None,
                messages=messages_with_query,
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
