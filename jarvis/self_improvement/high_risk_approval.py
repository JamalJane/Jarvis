"""
high_risk_approval.py — interactive diff display + yes/no prompt for High-risk improvements.

Blocks execution until the user makes an explicit choice.
"""

from jarvis.self_improvement.gemini_analyzer import Improvement

_G   = "\033[32m"
_Y   = "\033[33m"
_R   = "\033[31m"
_B   = "\033[1m"
_DIM = "\033[2m"
_RST = "\033[0m"


class HighRiskApprovalUI:
    """Display a colored unified diff of a High-risk improvement and ask for approval."""

    def prompt(self, imp: Improvement) -> bool:
        """
        Prints improvement details and blocks until the user types yes/no.
        Returns True to apply, False to skip.
        """
        print(f"\n  {'─' * 60}")
        print(f"  {_R}{_B}⚠  HIGH-RISK IMPROVEMENT #{imp.number}{_RST}")
        print(f"  {'─' * 60}")
        print(f"  {_B}File:{_RST}     {imp.file_path}")
        print(f"  {_B}Category:{_RST} {imp.category} | {_B}Severity:{_RST} {imp.severity}")
        print(f"  {_B}Problem:{_RST}  {imp.problem[:200]}")

        print(f"\n  {_B}Current code:{_RST}")
        for line in imp.current_code.strip().splitlines():
            print(f"  {_R}- {line}{_RST}")

        print(f"\n  {_B}Proposed fix:{_RST}")
        for line in imp.proposed_code.strip().splitlines():
            print(f"  {_G}+ {line}{_RST}")

        print(f"\n  {_B}Reasoning:{_RST} {imp.reasoning[:300]}")
        print(
            f"  {_DIM}Expected: +{imp.speed_estimate}% speed,"
            f" -{imp.token_estimate}% tokens{_RST}"
        )
        print(f"  {'─' * 60}")

        while True:
            print(f"  {_Y}Apply this high-risk change? [yes / no]{_RST} ", end="", flush=True)
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                print(f"\n  {_Y}Skipping (interrupted).{_RST}")
                return False

            if answer in ("yes", "y"):
                print(f"  {_G}✓ User approved — will test and apply.{_RST}")
                return True
            if answer in ("no", "n", "skip", "s"):
                print(f"  {_DIM}Skipped by user.{_RST}")
                return False
            print(f"  Please type 'yes' or 'no'.")
