# GenClash Arena

> On-chain arcade, judged by AI validators on **GenLayer**.

An on-chain arcade running on the **GenLayer Bradbury testnet**. Match
results are judged by AI validators through GenLayer's **Optimistic Democracy**
consensus, and XP is distributed on-chain via an Intelligent Contract.

Built for the *Mini-games for GenLayer's Community* mission:

- Multiplayer-ready (rooms keyed by wallet address; PvP-extensible).
- Match length 5-15 minutes (10 short levels, fast pace).
- Replayable weekly via an LLM-generated weekly theme/modifier.
- On-chain leaderboard for community XP distribution.
- Showcases Intelligent Contracts + Optimistic Democracy (AI judge).

## Repository layout

```
contracts/
  GenClashArena.py    # Intelligent Contract (Python, GenVM)
index.html            # Single-file frontend (canvas game + GenLayer wallet)
images/               # Assets
README.md             # You are here
```

## Network

| Setting               | Value                                       |
|-----------------------|---------------------------------------------|
| GenLayer RPC          | `https://rpc-bradbury.genlayer.com`         |
| Chain ID              | `4221` (`0x107d`)                           |
| Currency              | GEN                                         |
| Explorer              | `https://explorer-bradbury.genlayer.com`    |
| Faucet                | `https://testnet-faucet.genlayer.foundation`|

The frontend will auto-prompt the wallet to add/switch to this chain.

## Deploying the Intelligent Contract

The fastest path is **GenLayer Studio** (browser, no install):

1. Open <https://studio.genlayer.com>.
2. Create a new contract, paste the contents of `contracts/GenClashArena.py`.
3. Click *Deploy*. The constructor takes no arguments.
4. Copy the deployed contract address.

Alternative: deploy from your terminal with the GenLayer CLI / `genlayer-py`
SDK against Bradbury (`https://rpc-bradbury.genlayer.com`). See
<https://docs.genlayer.com/api-references/genlayer-cli>.

## Wiring the address into the frontend

Open `index.html`, find the `GenLayer integration` script block, and replace:

```js
const GENCLASH_CONTRACT = '0x0000000000000000000000000000000000000000';
```

with the real deployed address.

### Gameplay flow

1. **Connect wallet** → auto-install GenLayer Snap, switch to Bradbury.
2. **Start Match** → `pay_to_play` (0.0001 GEN) unlocks your current level.
3. **Play a level** → on win, `report_win` advances you; on loss, `report_loss` resets you to Level 1.
4. **Next Level** → another `pay_to_play` (0.0001 GEN) then play.
5. **Leaderboard** → on-chain ranking by highest level reached.

### Live deployment

| Field | Value |
|---|---|
| Contract address | _redeploy required after schema update (see below)_ |
| Network | GenLayer Bradbury (chain ID `4221`) |
| Entry fee | `0.0001 GEN` per level |

## Running locally

It is a single static file. Any static server works:

```powershell
# from the project root
python -m http.server 8080
```

Then visit <http://localhost:8080>, click **CONNECT WALLET**, approve the
GenLayer Bradbury chain in MetaMask, and **START GAME**.

## Match flow on-chain

1. **Connect** -> wallet signs `eth_requestAccounts` and switches to chain `0x107d`.
2. **Start Game** -> `pay_to_play()` (payable, 0.001 GEN). Validators accept
   the entry transaction.
3. **Play** the match (locally, fast and snappy).
4. **Win or lose** -> `record_result(player_score, ai_score, level, duration, summary)`.
   - The leader validator runs `gl.nondet.exec_prompt` with a strict scoring
     rubric and proposes an XP value `0..100`.
   - Other validators independently re-run the same prompt. They accept if
     their XP is within +/-12 of the leader's (Comparative Equivalence).
   - On consensus, XP is added to the player's on-chain balance.
5. **Leaderboard** -> any client can call `get_leaderboard()` to render the
   weekly ranking.

## Weekly replayability

`refresh_weekly_theme()` uses `gl.nondet.exec_prompt` to generate a new
gameplay modifier each week. Validators ensure the theme is well-formed and
non-abusive before accepting it. The frontend shows the theme on the start
screen so players know what's different this week.

## Dev notes

- The frontend uses `genlayer-js` from `esm.sh` so no bundler is required.
- The contract uses `gl.vm.run_nondet_unsafe` because the AI judge involves a
  per-validator LLM call - `strict_eq` would never converge.
- Anti-cheat: the contract clamps inputs, requires a paid session before
  `record_result`, and instructs the AI judge to set XP to 0 on cheating
  hints in the player's self-report.
