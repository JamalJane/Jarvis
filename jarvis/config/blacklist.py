from typing import List, Set
from jarvis.config.constants import BLACKLIST


class BlacklistChecker:
    def __init__(self):
        self.blacklisted_patterns: Set[str] = set(BLACKLIST)

    def is_blacklisted(self, action: str) -> bool:
        action_lower = action.lower()
        for pattern in self.blacklisted_patterns:
            if pattern in action_lower:
                return True
        return False

    def add_pattern(self, pattern: str):
        self.blacklisted_patterns.add(pattern.lower())

    def remove_pattern(self, pattern: str):
        self.blacklisted_patterns.discard(pattern.lower())

    def get_blacklist(self) -> List[str]:
        return list(self.blacklisted_patterns)

    def clear(self):
        self.blacklisted_patterns.clear()
