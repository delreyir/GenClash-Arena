# GenClashArena

**1v1 air-hockey, judged by AI validators on GenLayer.**

A best-of-three neon arcade where every match outcome is verified by an
LLM-powered AI judge running inside GenLayer's **Optimistic Democracy**
consensus. Solo level progression and **WebRTC P2P multiplayer rooms** share
the same on-chain pipeline: pay, play, get judged, climb the leaderboard.

Built for the *Mini-games for GenLayer's Community* mission. The whole game
is one static `index.html` + one Intelligent Contract.

---

## What is GenClashArena?

- A **canvas air-hockey** game with a paddle + puck across **10 increasingly
  hostile levels**, each adding new obstacles, mechanics or visual chaos.
- **Best of 3 rounds** per match: a round goes to the first player to **3
  goals**, the match to the first player to **2 rounds**. A full match lasts
  ~6–10 minutes, comfortably inside the GenLayer mission's 5–15 min window.
- **Two ways to play**:
  - **Solo** vs. an AI paddle that gets 10% smarter every level.
  - **Multiplayer 1v1** in a shared P2P room (WebRTC via PeerJS, no central
    game server, sub-100 ms tick).
- **Every result is judged on-chain.** When you win, the contract asks an
  LLM (re-executed by every validator) whether the score & duration are
  plausible. Only if the validators reach **Optimistic Democracy consensus
  on `valid: true`** does your level advance and your XP get awarded.
- **On-chain leaderboard** ranks players by highest level reached.

---

## How GenLayer is used

GenClashArena is intentionally a *thin frontend on a fat Intelligent
Contract* so the GenLayer-native parts are unambiguous.

| Concern | Where it lives | GenLayer primitive |
|---|---|---|
| Entry fee | `pay_to_play()` (payable, 0.0001 GEN) | Standard EVM-compatible tx |
| Match verdict | `report_win(score_us, score_ai, duration)` | **`gl.nondet.exec_prompt`** — a *non-deterministic LLM call* inside the contract, re-run by every validator under **Comparative Equivalence** |
| Loss | `report_loss()` | Deterministic reset; validators agree by `strict_eq` |
| Player state | `current_level`, `highest_level`, `xp` | On-chain `TreeMap[Address, ...]` |
| Leaderboard | `get_leaderboard()` | Read-only contract call (no gas) |
| PvP entry | Both peers call `pay_to_play()` *before* the lobby opens | Same path as solo |

The AI judge is the canonical use-case for GenLayer's Optimistic Democracy:
a subjective question ("was this match score plausible?") that no single
oracle could answer, but that a *committee of validators each running an
LLM independently* can.

---

## Features

### Gameplay
- 10 unique levels (spinning bars, oscillating obstacles, hex grids, scaling
  puck, slow-time pickups, dual-bar gauntlets, etc.).
- Best-of-3 rounds, ~6–10 min per match.
- Bottom-paddle touch / mouse / drag controls. Mobile-first sizing.
- Side panels: **HOW TO PLAY**, **RULES**, **LEGEND**, and a live **AI
  JUDGE** panel that streams tx status from the contract.

### Multiplayer (1v1 rooms)
- **Create Room** → contract entry fee tx → unique room code (e.g.
  `GENCLASH-X4F7K`) → click to copy → share with a friend.
- **Join Room** → enter code → contract entry fee tx → WebRTC handshake.
- **Host-authoritative physics**: the host runs the puck simulation and
  broadcasts state every animation frame; the client streams its paddle
  position back. Both peers see themselves at the bottom (coordinate frame
  is flipped client-side).
- After the match, **both peers submit on-chain** via `report_win` /
  `report_loss`. The winner triggers the AI Judge, just like in solo.
- Disconnect handling, copy-to-clipboard room code, timeout fallback.

### On-chain
- 100% of progression, scoring acceptance and the leaderboard live on
  Bradbury. Nothing about a player's record is stored off-chain.
- The frontend never marks a level as won locally — it waits for the
  validators' decision, then re-reads `get_current_level`.

### Leaderboard
- `get_leaderboard()` returns top N players sorted by highest level.
- Overlay shows rank, address, level reached, and XP earned.
- Refresh button re-queries the chain on demand.

---

## Repository layout

```
contracts/
  GenClashArena.py    # Intelligent Contract (Python, GenVM)
index.html            # Single-file frontend (canvas + wallet + WebRTC)
README.md             # You are here
```

The frontend has zero build step. Open the file, point a wallet at it, play.

---

## Architecture at a glance

```
                          ┌────────────────────────────────────┐
                          │       GenLayer Bradbury chain      │
   wallet tx ───────────▶│   GenClashArena Intelligent Contract│
                          │  - pay_to_play  (payable)          │
                          │  - report_win   (gl.nondet.exec_prompt)
                          │  - report_loss                     │
                          │  - get_leaderboard / get_*_level   │
                          └────────────────┬───────────────────┘
                                           │ tx hash + status
                          ┌────────────────▼───────────────────┐
                          │           index.html               │
                          │   genlayer-js (esm.sh) · canvas    │
                          │   AI-Judge panel polls tx status   │
                          └──────────────┬──────────┬──────────┘
                                         │          │ WebRTC DataChannel
                                         │          │ (PeerJS broker for
                                         │          │  signalling only)
                                         │   ┌──────▼──────┐
                                         │   │  Peer (opp.)│
                                         │   └─────────────┘
                                  (single browser, solo mode)
```

---

## Network

| Setting   | Value |
|-----------|-------|
| RPC       | `https://rpc-bradbury.genlayer.com` |
| Chain ID  | `4221` (`0x107d`) |
| Currency  | GEN |
| Explorer  | `https://explorer-bradbury.genlayer.com` |
| Faucet    | `https://testnet-faucet.genlayer.foundation` |

The frontend auto-prompts the wallet to add / switch to this chain on
connect.

## Live deployment

| Field            | Value |
|------------------|-------|
| Contract address | `0xFb14a90D77dd31Bb65Eb8CA97BE2C43C5d0E7E0e` |
| Network          | GenLayer Bradbury (chain ID `4221`) |
| Entry fee        | `0.0001 GEN` per match |
| Explorer         | <https://explorer-bradbury.genlayer.com/address/0xFb14a90D77dd31Bb65Eb8CA97BE2C43C5d0E7E0e> |

---

## Running locally

It's a single static file. Any static server works:

```powershell
# from the project root
python -m http.server 8080
```

Then visit <http://localhost:8080>, click **CONNECT WALLET**, approve the
Bradbury chain in your wallet, and **START MATCH** (solo) or
**⚡ MULTIPLAYER (1v1)** (P2P).

### Multiplayer in 30 seconds

1. Both players open the site and connect their wallets.
2. Player A clicks ⚡ Multiplayer → **Create Room** → approves the 0.0001 GEN
   entry tx → copies the `GENCLASH-XXXXX` code.
3. Player B clicks ⚡ Multiplayer → **Join Room** → pastes the code →
   approves their own entry tx.
4. Match starts. First to 2 rounds wins. Both peers submit the result
   on-chain at the end and the AI Judge verifies the winner.

---

## Deploying your own copy of the contract

The fastest path is **GenLayer Studio**:

1. Open <https://studio.genlayer.com>.
2. Create a new contract, paste the contents of
   `contracts/GenClashArena.py`.
3. Click *Deploy* (constructor takes no arguments).
4. Copy the deployed address.

Alternative: deploy from your terminal with the GenLayer CLI or the
`genlayer-py` SDK against Bradbury. See
<https://docs.genlayer.com/api-references/genlayer-cli>.

Then open `index.html`, find the `GenLayer integration` script block, and
replace the address:

```js
const GENCLASH_CONTRACT = '0xYOUR_ADDRESS_HERE';
```

---

## Dev notes

- The frontend imports `genlayer-js` directly from `esm.sh`, so no bundler
  is required — it's truly *one file*.
- The contract relies on `gl.nondet.exec_prompt` for the AI judge call;
  validators run the LLM independently and accept via Optimistic Democracy
  (a per-validator quorum on the judge's `{valid, reason}` JSON).
- The frontend polls `getTransaction` for the judge tx, surfaces the LLM
  verdict in the WIN overlay *and* in the persistent side AI-Judge panel,
  and links to the explorer for full transparency.
- WebRTC signalling uses the **free public PeerJS broker**. Game state
  itself is fully peer-to-peer, so the broker only sees the room code, not
  any gameplay.
- The HTML is `dir="ltr"` even though parts of the codebase carry Darija
  comments — the rendering direction is enforced LTR everywhere.

---

## License

MIT — do whatever you like, just don't claim you were the first to put an
LLM referee inside an air-hockey paddle.

