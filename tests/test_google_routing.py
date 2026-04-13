"""
Quick smoke test for Google intent classification and direct dispatch.
Does NOT start the full TUI -- just exercises the routing logic.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import os
import sys
os.environ.setdefault("PINECONE_API_KEY", "")  # prevent crash if not set

from unittest.mock import MagicMock, patch

# ── patch heavy deps so we don't need a running Chrome / audio etc. ──────────
sys.modules.setdefault("pyautogui", MagicMock())
sys.modules.setdefault("pyttsx3",   MagicMock())
sys.modules.setdefault("speech_recognition", MagicMock())

from jarvis.main_loop import Jarvis

def make_jarvis():
    with patch("jarvis.main_loop.PineconeStore"), \
         patch("jarvis.main_loop.BrowserController"), \
         patch("jarvis.main_loop.AutomationController"), \
         patch("jarvis.main_loop.VoiceIO"), \
         patch("jarvis.main_loop.GoogleServices") as MockGS, \
         patch("jarvis.main_loop.SelfImprovementAgent"), \
         patch("jarvis.main_loop.SessionLock"), \
         patch("jarvis.main_loop.LocalMemoryStore"), \
         patch("jarvis.memory.pinecone_store.PineconeStore"):
        mock_gs = MagicMock()
        mock_gs.is_authenticated.return_value = True
        MockGS.return_value = mock_gs
        j = Jarvis()
    return j

def test_classify():
    j = make_jarvis()
    cases = {
        "send an email to bob@test.com saying hi":  "email",
        "email bob@test.com and tell him I'm late": "email",
        "check my calendar":                        "calendar",
        "do i have any meetings today":             "calendar",
        "create a doc called Sprint Notes":         "doc",
        "new document for the project":             "doc",
        "open youtube":                             "",     # should NOT match
        "what time is it":                          "",     # should NOT match
    }
    all_ok = True
    for query, expected in cases.items():
        got = j._classify_google_intent(query)
        status = "✅" if got == expected else "❌"
        if got != expected:
            all_ok = False
        print(f"  {status}  [{expected or 'none':8}] expected  [{got or 'none':8}] got  |  '{query}'")
    return all_ok

if __name__ == "__main__":
    print("\n── Google intent classifier ──────────────────────────────────────")
    ok = test_classify()
    print("\nResult:", "ALL PASS ✅" if ok else "SOME FAILURES ❌")
