"""Core game logic for Truth or Dare: Player, PromptManager, and Game.

This module is plain Python with zero web or GUI dependencies, so the
exact same rules power the Flask API layer (app.py) and could equally
power a desktop GUI or a test suite.
"""

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

MAX_SKIPS = 3
CATEGORY_ORDER = ["Normal Truth", "Spicy Truth", "Normal Dare", "Spicy Dare"]


@dataclass
class Player:
    """Represents a single player and their running statistics.

    Attributes:
        name: The player's display name.
        skips_remaining: Single skips left for the entire game (starts at MAX_SKIPS).
        completed_count: Number of prompts this player has completed.
        skips_used: Number of single skips this player has used.
        double_skips_used: Number of double skips this player has used.
    """

    name: str
    skips_remaining: int = MAX_SKIPS
    completed_count: int = 0
    skips_used: int = 0
    double_skips_used: int = 0

    def to_dict(self) -> dict:
        """Serialize this player to a plain dictionary for JSON storage."""
        return {
            "name": self.name,
            "skips_remaining": self.skips_remaining,
            "completed_count": self.completed_count,
            "skips_used": self.skips_used,
            "double_skips_used": self.double_skips_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Player":
        """Reconstruct a Player from a dictionary produced by to_dict()."""
        return cls(
            name=data["name"],
            skips_remaining=data.get("skips_remaining", MAX_SKIPS),
            completed_count=data.get("completed_count", 0),
            skips_used=data.get("skips_used", 0),
            double_skips_used=data.get("double_skips_used", 0),
        )


class PromptManager:
    """Owns the prompt pools for all four categories and all random draws.

    Each category keeps one mutable pool (a list). Drawing a prompt removes
    one instance from the pool. Skipping a prompt puts it back *plus* one
    extra copy, which increases the probability it's drawn again later --
    a simple, transparent way to implement weighted random selection using
    nothing more exotic than random.choice on a list with duplicates.
    """

    def __init__(self, file_paths: Dict[str, str]) -> None:
        """Load every category's prompt file.

        Args:
            file_paths: Mapping of category name -> path to a UTF-8 text
                file containing one prompt per line.

        Raises:
            FileNotFoundError: If any configured file does not exist.
            UnicodeDecodeError: If a file is not valid UTF-8 text.
        """
        self.file_paths: Dict[str, str] = dict(file_paths)
        self.pools: Dict[str, List[str]] = {}
        self.total_loaded: Dict[str, int] = {}
        self.completed_count: int = 0

        for category in CATEGORY_ORDER:
            path = self.file_paths.get(category)
            prompts = self._load_file(path) if path else []
            self.pools[category] = prompts
            self.total_loaded[category] = len(prompts)

    @staticmethod
    def _load_file(path: str) -> List[str]:
        """Read a prompt file, returning one cleaned-up entry per non-blank line."""
        file_path = Path(path)
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                raw_lines = handle.readlines()
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Prompt file not found: {path}. Make sure it exists in the "
                "prompts/ folder before deploying."
            ) from exc
        except UnicodeDecodeError as exc:
            raise UnicodeDecodeError(
                exc.encoding, exc.object, exc.start, exc.end,
                f"File is not valid UTF-8 text: {path}",
            ) from exc

        return [line.strip() for line in raw_lines if line.strip()]

    # ---------------- Drawing prompts ----------------
    def draw(self, category: str) -> Optional[str]:
        """Randomly remove and return one prompt from `category`, or None if empty."""
        pool = self.pools.get(category, [])
        if not pool:
            return None
        prompt = random.choice(pool)
        pool.remove(prompt)
        return prompt

    def return_with_weight(self, category: str, prompt: str) -> None:
        """Put a skipped prompt back into its pool with increased weight.

        Two copies are added: one to restore the prompt to the pool, and a
        second so its odds of being drawn again go up. Repeated skips keep
        stacking additional copies.
        """
        self.pools.setdefault(category, [])
        self.pools[category].append(prompt)
        self.pools[category].append(prompt)

    def mark_completed(self) -> None:
        """Increment the global completed-prompt counter."""
        self.completed_count += 1

    # ---------------- Queries ----------------
    def is_empty(self, category: str) -> bool:
        """Return True if `category` has no prompts left to draw."""
        return len(self.pools.get(category, [])) == 0

    def all_empty(self) -> bool:
        """Return True if every category is out of prompts."""
        return all(self.is_empty(c) for c in CATEGORY_ORDER)

    def counts_by_category(self) -> Dict[str, int]:
        """Return the number of distinct prompts remaining per category.

        Duplicate copies added by skipping are a weighting mechanism only,
        so they are not counted twice here.
        """
        return {category: len(set(pool)) for category, pool in self.pools.items()}

    # ---------------- Persistence ----------------
    def to_dict(self) -> dict:
        """Serialize full manager state (pools, paths, completed count) to a JSON-safe dict."""
        return {
            "file_paths": self.file_paths,
            "pools": self.pools,
            "completed_count": self.completed_count,
            "total_loaded": self.total_loaded,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromptManager":
        """Reconstruct a PromptManager from to_dict() output without re-reading files."""
        manager = cls.__new__(cls)
        manager.file_paths = data["file_paths"]
        manager.pools = {category: list(prompts) for category, prompts in data["pools"].items()}
        manager.completed_count = data.get("completed_count", 0)
        manager.total_loaded = data.get("total_loaded", {c: len(v) for c, v in manager.pools.items()})
        return manager


class Game:
    """Coordinates players, turn order, and prompt delivery for one session.

    Skip and Double Skip both stay within the *same category* that was
    chosen for the current turn:
      - Skip returns the prompt to its pool (with extra weight) and
        immediately draws a new prompt from that same category.
      - Double Skip discards the current prompt for good and forces two
        more prompts from that same category, back to back, before the
        turn can pass to the next player.
    Neither ever hands the player a fresh category choice mid-turn -- only
    finishing a turn with no forced prompts left returns to the category
    picker, and only then for the next player.
    """

    def __init__(self, prompt_manager: PromptManager) -> None:
        self.prompt_manager: PromptManager = prompt_manager
        self.players: List[Player] = []
        self.current_player_index: int = 0

        # Currently displayed prompt (None means "show the category picker").
        self.current_category: Optional[str] = None
        self.current_prompt: Optional[str] = None

        # Extra prompts still owed in the current category before the turn
        # can pass on. Populated by Double Skip (always same-category,
        # auto-drawn -- never a fresh player choice).
        self.forced_queue: List[str] = []

        self.started: bool = False
        self.game_over: bool = False

    # ---------------- Player management ----------------
    def add_player(self, name: str) -> None:
        """Add a new player by name. Raises ValueError on an empty name."""
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Player name cannot be empty.")
        self.players.append(Player(name=cleaned))

    def remove_player(self, index: int) -> None:
        """Remove the player at `index`, if it exists."""
        if 0 <= index < len(self.players):
            self.players.pop(index)
            if self.current_player_index >= len(self.players) and self.players:
                self.current_player_index = 0

    def shuffle_players(self) -> None:
        """Randomize player order (only meaningful before the game starts)."""
        random.shuffle(self.players)

    def can_start(self) -> bool:
        """Return True once there are at least two players."""
        return len(self.players) >= 2

    def start_game(self) -> None:
        """Begin the game at player 0. Raises ValueError if not enough players."""
        if not self.can_start():
            raise ValueError("Need at least two players to start.")
        self.started = True
        self.current_player_index = 0

    @property
    def current_player(self) -> Optional[Player]:
        """The Player whose turn it currently is, or None before the game starts."""
        if not self.players:
            return None
        return self.players[self.current_player_index]

    # ---------------- Turn flow ----------------
    def choose_category(self, category: str) -> Optional[str]:
        """Draw a prompt for `category` and make it the active prompt.

        Returns the prompt text, or None if that category is empty.
        """
        prompt = self.prompt_manager.draw(category)
        if prompt is None:
            return None
        self.current_category = category
        self.current_prompt = prompt
        return prompt

    def complete_current(self) -> None:
        """Mark the active prompt as completed and move on.

        If Double Skip queued more same-category prompts for this turn,
        the next one is served immediately; otherwise play passes to the
        next player.
        """
        if self.current_prompt is None:
            return
        self.current_player.completed_count += 1
        self.prompt_manager.mark_completed()

        if self.forced_queue:
            self.current_prompt = self.forced_queue.pop(0)
            # current_category stays the same -- it's a forced repeat.
        else:
            self.current_category = None
            self.current_prompt = None
            self._rotate_player()

        if self.prompt_manager.all_empty():
            self.game_over = True

    def skip_current(self) -> bool:
        """Skip the active prompt (single skip).

        The skipped prompt goes back into its pool with extra weight, and
        a new prompt is drawn automatically from that *same* category --
        the turn stays with the current player and no category picker is
        shown. Returns False (and changes nothing) if the current player
        has no skips left.
        """
        if self.current_prompt is None:
            return False
        player = self.current_player
        if player.skips_remaining <= 0:
            return False

        player.skips_remaining -= 1
        player.skips_used += 1
        category = self.current_category
        self.prompt_manager.return_with_weight(category, self.current_prompt)

        new_prompt = self.prompt_manager.draw(category)
        if new_prompt is not None:
            self.current_prompt = new_prompt
        elif self.forced_queue:
            # That category just ran dry; fall through to whatever is
            # still queued from an earlier Double Skip (same category).
            self.current_prompt = self.forced_queue.pop(0)
        else:
            self.current_category = None
            self.current_prompt = None
            self._rotate_player()

        if self.prompt_manager.all_empty():
            self.game_over = True
        return True

    def double_skip_current(self) -> None:
        """Permanently discard the active prompt and force two more of the
        *same* category, back to back, in this same turn.

        The current prompt is not returned to any pool -- it is gone for
        good. Two fresh prompts are drawn automatically from the same
        category (no player choice involved) and must both be completed
        before the turn passes on. There is no limit on how many times
        Double Skip can be used.
        """
        if self.current_prompt is None:
            return
        self.current_player.double_skips_used += 1
        category = self.current_category
        # The discarded prompt was already removed from its pool when it
        # was drawn, so nothing further is needed to erase it permanently.

        replacements: List[str] = []
        for _ in range(2):
            drawn = self.prompt_manager.draw(category)
            if drawn is not None:
                replacements.append(drawn)

        if replacements:
            self.current_category = category
            self.current_prompt = replacements[0]
            self.forced_queue = replacements[1:] + self.forced_queue
        elif self.forced_queue:
            # Category is now empty, but earlier queued same-category
            # prompts (from a previous Double Skip) are still owed.
            self.current_prompt = self.forced_queue.pop(0)
        else:
            self.current_category = None
            self.current_prompt = None
            self._rotate_player()

        if self.prompt_manager.all_empty():
            self.game_over = True

    def _rotate_player(self) -> None:
        """Advance current_player_index to the next player, wrapping around."""
        if self.players:
            self.current_player_index = (self.current_player_index + 1) % len(self.players)

    # ---------------- Client-facing state ----------------
    def state_for_client(self) -> dict:
        """Build the JSON-serializable snapshot the front end renders from."""
        if not self.started:
            screen = "setup"
        elif self.game_over:
            screen = "game_over"
        else:
            screen = "game"

        player = self.current_player
        return {
            "screen": screen,
            "players": [p.to_dict() for p in self.players],
            "current_player_index": self.current_player_index,
            "current_player_name": player.name if player else None,
            "current_category": self.current_category,
            "current_prompt": self.current_prompt,
            "forced_queue_length": len(self.forced_queue),
            "counts_by_category": self.prompt_manager.counts_by_category(),
            "category_is_empty": {c: self.prompt_manager.is_empty(c) for c in CATEGORY_ORDER},
            "completed_total": self.prompt_manager.completed_count,
            "can_start": self.can_start(),
            "started": self.started,
            "game_over": self.game_over,
        }

    # ---------------- Full save / load ----------------
    def to_dict(self) -> dict:
        """Serialize complete game state (for the Save Game download)."""
        return {
            "players": [p.to_dict() for p in self.players],
            "current_player_index": self.current_player_index,
            "current_category": self.current_category,
            "current_prompt": self.current_prompt,
            "forced_queue": self.forced_queue,
            "started": self.started,
            "game_over": self.game_over,
            "prompt_manager": self.prompt_manager.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Game":
        """Reconstruct a full Game (for Load Game) from to_dict() output."""
        game = cls(PromptManager.from_dict(data["prompt_manager"]))
        game.players = [Player.from_dict(p) for p in data["players"]]
        game.current_player_index = data.get("current_player_index", 0)
        game.current_category = data.get("current_category")
        game.current_prompt = data.get("current_prompt")
        game.forced_queue = list(data.get("forced_queue", []))
        game.started = data.get("started", False)
        game.game_over = data.get("game_over", False)
        return game
