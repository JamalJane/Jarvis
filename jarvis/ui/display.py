import sys


class Display:
    @staticmethod
    def greeting(username: str, summary: str = ""):
        print(f"\n{'=' * 50}")
        print(f"Hello {username} 👋")
        print(f"{'=' * 50}")
        if summary:
            print(f"\n{summary}")
        print("\nAPI Status:")
        print("-" * 30)

    @staticmethod
    def prompt():
        print("\nWhat do you need? ", end="")

    @staticmethod
    def status(message: str):
        print(f"[STATUS] {message}")

    @staticmethod
    def error(message: str):
        print(f"[ERROR] {message}", file=sys.stderr)

    @staticmethod
    def success(message: str):
        print(f"[✓] {message}")

    @staticmethod
    def warning(message: str):
        print(f"[⚠] {message}")
