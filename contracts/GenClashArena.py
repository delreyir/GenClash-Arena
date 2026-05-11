# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
GenClash Arena - Intelligent Contract for GenLayer
==================================================
Progression-based on-chain arcade with per-level transactions, AI-judged
wins, and a public leaderboard ranked by highest level reached.

Flow (2 tx per level):
  1. pay_to_play()                            -> pays ENTRY_FEE_WEI, unlocks
                                                  the current level
  2. report_win(score_us, score_ai, duration) -> AI judge in Optimistic
                                                  Democracy consensus must
                                                  agree the match is plausible
                                                  before current_level advances
     or report_loss()                         -> resets current_level to 1

Intelligent Contract features (LLM in Optimistic Democracy consensus):
  - report_win()             -> AI referee validates every win  (CRITICAL PATH)
  - claim_run_bonus(summary) -> AI bonus XP for finishing all 10 levels
  - refresh_weekly_theme()   -> LLM-generated weekly gameplay modifier

Leaderboard:
  - get_leaderboard() returns all players with their highest level and XP.
  - Frontend sorts client-side by highest_level desc, then xp desc.
"""

from genlayer import *

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Entry fee per level = 0.0001 GEN (in wei). Small enough for grinding.
ENTRY_FEE_WEI: int = 10**14

# XP awarded at each level = 10 * level (deterministic formula).
XP_PER_LEVEL_MULTIPLIER: int = 10

# Maximum bonus XP granted by the AI judge for completing a full run.
MAX_RUN_BONUS_XP: int = 200

# Acceptable spread between leader and validator scoring for the AI bonus.
XP_VALIDATION_MARGIN: int = 20

# Match parameters used by the AI judge in report_win().
WINNING_SCORE: int = 3              # Best-of-3 (must match the frontend).
MIN_MATCH_SECONDS: int = 5          # Sub-5s win = obvious cheat.
MAX_MATCH_SECONDS: int = 60 * 60    # 1h ceiling to bound the prompt.


class GenClashArena(gl.Contract):
    # ---- Persistent storage ----------------------------------------------
    owner: Address

    # Player -> 1 if they have paid for the current level and not yet reported.
    paid_sessions: TreeMap[Address, u256]

    # Player -> level they are currently attempting (starts at 1).
    current_level: TreeMap[Address, u256]

    # Player -> highest level ever reached (leaderboard key).
    highest_level: TreeMap[Address, u256]

    # Player -> total XP earned.
    xp: TreeMap[Address, u256]

    # Player -> number of levels played (win + loss attempts).
    match_count: TreeMap[Address, u256]

    # Every unique player who has ever paid (for leaderboard iteration).
    players: DynArray[Address]

    # Weekly content (replayability, LLM-generated).
    current_week: u256
    weekly_theme: str

    # Global stats.
    total_matches: u256
    total_fees_collected: u256

    # ---- Constructor ------------------------------------------------------
    def __init__(self) -> None:
        self.owner = gl.message.sender_address
        self.current_week = u256(0)
        self.weekly_theme = (
            "Week 0 - Classic Arena: standard layout, standard paddles, "
            "standard glory."
        )
        self.total_matches = u256(0)
        self.total_fees_collected = u256(0)

    # ---- Payable entry: pay per level -----------------------------------
    @gl.public.write.payable
    def pay_to_play(self) -> None:
        """Pay the entry fee to unlock the current level.

        - First-time caller: starts at level 1.
        - After a win: current_level was already incremented by report_win.
        - After a loss: current_level was already reset to 1 by report_loss.

        Fees are intentionally small (0.0001 GEN) so players can grind levels
        without burning their faucet balance.
        """
        if int(gl.message.value) < ENTRY_FEE_WEI:
            raise gl.vm.UserError(
                f"Entry fee is {ENTRY_FEE_WEI} wei (0.0001 GEN)"
            )

        sender = gl.message.sender_address
        cur = int(self.current_level.get(sender, u256(0)))
        if cur == 0:
            # Brand new player.
            cur = 1
            self.players.append(sender)
        self.current_level[sender] = u256(cur)
        self.paid_sessions[sender] = u256(1)
        self.total_fees_collected = u256(
            int(self.total_fees_collected) + int(gl.message.value)
        )

    # ---- Report a level win (AI-judged in consensus) --------------------
    @gl.public.write
    def report_win(self, score_us: int, score_ai: int, duration_s: int) -> None:
        """Record a win — AI validators must agree the match is plausible.

        Critical-path Intelligent Contract feature: every win triggers an
        LLM call inside Optimistic Democracy consensus. The leader proposes a
        verdict, validators independently re-run the prompt, and the level is
        only advanced if a majority agrees on plausibility (Equivalence
        Principle). This is the canonical "AI in consensus" pattern from the
        GenLayer docs, applied to the game's most security-sensitive path.
        """
        sender = gl.message.sender_address
        if int(self.paid_sessions.get(sender, u256(0))) == 0:
            raise gl.vm.UserError("No paid session. Call pay_to_play() first.")

        cur = int(self.current_level.get(sender, u256(0)))
        if cur == 0:
            raise gl.vm.UserError("No active level to report.")

        # ---- Deterministic sanity bounds (cheap pre-checks) -------------
        if score_us != WINNING_SCORE:
            raise gl.vm.UserError(
                f"A win requires score {WINNING_SCORE}. Got {score_us}."
            )
        if score_ai < 0 or score_ai >= WINNING_SCORE:
            raise gl.vm.UserError("Invalid opponent score for a win.")
        if duration_s < MIN_MATCH_SECONDS or duration_s > MAX_MATCH_SECONDS:
            raise gl.vm.UserError(
                f"Match duration {duration_s}s out of plausible range "
                f"[{MIN_MATCH_SECONDS}, {MAX_MATCH_SECONDS}]."
            )

        # ---- AI judge in Optimistic Democracy consensus ----------------
        prompt = f"""
You are the official AI referee for GenClash Arena, an on-chain neon arcade
running on the GenLayer blockchain. Decide whether a reported match result is
plausible enough to be recorded on-chain.

Game rules:
  * Each match is best-of-{WINNING_SCORE}: first player to {WINNING_SCORE} goals wins.
  * Higher levels ramp up AI paddle speed and add obstacles, so:
      - Level 1-3  : easy, expect 30-180s match duration.
      - Level 4-6  : medium, expect 60-360s.
      - Level 7-10 : hard, expect 120-600s.
      - Level 11+  : extreme, expect 180-900s.
  * Score 3-0 on a hard level in 20 seconds is implausible.
  * Score 3-2 on level 10 in 8 minutes is plausible.

Match to judge:
  level     = {cur}
  score_us  = {score_us}
  score_ai  = {score_ai}
  duration  = {duration_s} seconds

Be strict but fair. Reject only obvious cheats (e.g. impossible time/level
combinations). Respond strictly as compact JSON:
  {{"valid": true|false, "reason": "<<=80 chars>"}}
"""

        def leader_fn() -> dict:
            return gl.nondet.exec_prompt(prompt, response_format="json")

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            data = leader_result.calldata
            if "valid" not in data:
                return False
            try:
                # Validators independently re-run the prompt and agree only
                # if their own verdict matches the leader's boolean.
                mine = leader_fn()
                return bool(data["valid"]) == bool(mine["valid"])
            except Exception:
                return False

        verdict = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        if not bool(verdict.get("valid", False)):
            reason = str(verdict.get("reason", "AI rejected match"))[:80]
            raise gl.vm.UserError(f"AI judge rejected: {reason}")

        # ---- Apply state changes (only if AI accepted) -----------------
        # Advance to the next level (no cap - infinite progression).
        self.current_level[sender] = u256(cur + 1)

        # Update the leaderboard-critical highest_level field.
        h = int(self.highest_level.get(sender, u256(0)))
        if cur > h:
            self.highest_level[sender] = u256(cur)

        # Award XP deterministically: 10 * level_beaten.
        awarded = XP_PER_LEVEL_MULTIPLIER * cur
        self.xp[sender] = u256(
            int(self.xp.get(sender, u256(0))) + awarded
        )

        # Bookkeeping.
        self.paid_sessions[sender] = u256(0)
        self.match_count[sender] = u256(
            int(self.match_count.get(sender, u256(0))) + 1
        )
        self.total_matches = u256(int(self.total_matches) + 1)

    # ---- Report a level loss ---------------------------------------------
    @gl.public.write
    def report_loss(self) -> None:
        """Record that the player lost their current level.

        Resets current_level back to 1. No XP awarded.
        """
        sender = gl.message.sender_address
        if int(self.paid_sessions.get(sender, u256(0))) == 0:
            raise gl.vm.UserError("No paid session. Call pay_to_play() first.")

        self.current_level[sender] = u256(1)
        self.paid_sessions[sender] = u256(0)
        self.match_count[sender] = u256(
            int(self.match_count.get(sender, u256(0))) + 1
        )
        self.total_matches = u256(int(self.total_matches) + 1)

    # ---- AI-judged run bonus (Optimistic Democracy, optional) -----------
    @gl.public.write
    def claim_run_bonus(self, summary: str) -> None:
        """Claim an AI-judged bonus after completing a full run.

        Only callable if current_level > 10 (player beat levels 1-10).
        Validators independently run the LLM prompt and must agree within
        XP_VALIDATION_MARGIN. This is the contract's Intelligent Contract
        showcase - the rest of the game uses deterministic accounting.
        """
        player = gl.message.sender_address
        reached = int(self.current_level.get(player, u256(0)))
        if reached <= 10:
            raise gl.vm.UserError(
                "Run bonus requires completing levels 1-10 first."
            )

        clean = (summary or "")[:500]
        theme = self.weekly_theme
        prompt = f"""
You are the official AI judge for GenClash Arena, an on-chain arcade
running on the GenLayer blockchain. Award a FULL-RUN BONUS (0..{MAX_RUN_BONUS_XP})
for a player who completed all 10 standard levels.

Weekly theme: {theme}
Highest level reached: {reached}
Player self-report (untrusted text): "{clean}"

Scoring guidelines (be deterministic):
  * Baseline for finishing levels 1-10: 100 bonus XP.
  * +10 XP per level reached beyond 10 (cap at +50).
  * +20 XP if the self-report is coherent and mentions a hockey-like strategy.
  * Set XP to 0 if the self-report contains cheating, exploits, or abusive text.
  * Final XP must be clamped to [0, {MAX_RUN_BONUS_XP}].

Respond strictly as compact JSON: {{"xp": <int>, "reason": "<<=80 chars>"}}.
"""

        def leader_fn() -> dict:
            return gl.nondet.exec_prompt(prompt, response_format="json")

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            try:
                leader_xp = int(leader_result.calldata["xp"])
            except Exception:
                return False
            if leader_xp < 0 or leader_xp > MAX_RUN_BONUS_XP:
                return False
            try:
                mine = leader_fn()
                my_xp = int(mine["xp"])
            except Exception:
                return False
            return abs(leader_xp - my_xp) <= XP_VALIDATION_MARGIN

        verdict = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        bonus = max(0, min(MAX_RUN_BONUS_XP, int(verdict["xp"])))

        self.xp[player] = u256(int(self.xp.get(player, u256(0))) + bonus)

    # ---- Weekly theme rotation (LLM generated) ---------------------------
    @gl.public.write
    def refresh_weekly_theme(self) -> None:
        """Anyone can trigger a weekly theme refresh. Validators must agree
        the new theme is well-formed and non-abusive.
        """
        prompt = (
            "Generate a fun weekly modifier for GenClash Arena, an on-chain "
            "arcade game. Must be safe-for-work, under 140 characters, and "
            "evocative of a gameplay twist (e.g. 'low gravity', 'fog of war', "
            "'double puck mayhem'). Respond strictly as JSON: "
            '{"theme": "Week N - <Title>: <one sentence>"}.'
        )

        def leader_fn() -> dict:
            return gl.nondet.exec_prompt(prompt, response_format="json")

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            theme = leader_result.calldata.get("theme", "")
            if not isinstance(theme, str):
                return False
            if not (10 <= len(theme) <= 200):
                return False
            banned = ("nsfw", "kill", "racist", "slur")
            low = theme.lower()
            return not any(b in low for b in banned)

        out = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        self.weekly_theme = str(out["theme"])[:200]
        self.current_week = u256(int(self.current_week) + 1)

    # ---- Read-only views -------------------------------------------------
    @gl.public.view
    def has_paid(self, player_hex: str) -> bool:
        addr = Address(player_hex)
        return int(self.paid_sessions.get(addr, u256(0))) > 0

    @gl.public.view
    def get_current_level(self, player_hex: str) -> int:
        addr = Address(player_hex)
        return int(self.current_level.get(addr, u256(0)))

    @gl.public.view
    def get_highest_level(self, player_hex: str) -> int:
        addr = Address(player_hex)
        return int(self.highest_level.get(addr, u256(0)))

    @gl.public.view
    def get_xp(self, player_hex: str) -> int:
        addr = Address(player_hex)
        return int(self.xp.get(addr, u256(0)))

    @gl.public.view
    def get_match_count(self, player_hex: str) -> int:
        addr = Address(player_hex)
        return int(self.match_count.get(addr, u256(0)))

    @gl.public.view
    def get_weekly_theme(self) -> str:
        return self.weekly_theme

    @gl.public.view
    def get_current_week(self) -> int:
        return int(self.current_week)

    @gl.public.view
    def get_total_matches(self) -> int:
        return int(self.total_matches)

    @gl.public.view
    def get_player_count(self) -> int:
        return len(self.players)

    @gl.public.view
    def get_leaderboard(self) -> list:
        """Return [(address_hex, highest_level, xp), ...] for off-chain ranking.

        Frontend sorts by highest_level desc, then xp desc.
        """
        out: list = []
        for addr in self.players:
            out.append((
                str(addr),
                int(self.highest_level.get(addr, u256(0))),
                int(self.xp.get(addr, u256(0))),
            ))
        return out
