from jarvis.ui.display import Display

HELP_TEXT = """
═══════════════════════════════════════════════════════════════
HELP & COMMANDS
═══════════════════════════════════════════════════════════════

VOICE COMMANDS:
  [Press Enter]         - Start listening
  [Press Enter again]   - Stop listening

TEXT INPUT:
  [type text]           - Text query
  screenshot [prompt]   - Screenshot analysis

CONTROL:
  open browser          - Open browser manually
  done                  - End current task
  stop                  - Abort all tasks
  resume                - Continue paused task
  /help                 - Show this help
  /history              - 7-day activity summary

EXAMPLES:
  search reddit for monke
  extract top 5 posts with votes
  go to github.com
  click the login button

═══════════════════════════════════════════════════════════════
"""


def show_help():
    print(HELP_TEXT)


def handle_help_command(command: str) -> bool:
    if command.strip().lower() in ["/help", "help", "?"]:
        show_help()
        return True
    return False


def is_help_command(command: str) -> bool:
    return command.strip().lower() in ["/help", "help", "?", "help me"]
