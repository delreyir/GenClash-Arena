# GenClash Arena — GenLayer Conformance Report

> A line-by-line mapping of how this project implements every requirement from
> the official GenLayer docs, so the GenLayer team can audit the build at a
> glance.

- **Live app:** <https://gen-clash-arena.vercel.app>
- **Repo:** <https://github.com/delreyir/GenClash-Arena>
- **Network:** GenLayer Bradbury Testnet (chain ID `4221`, RPC `https://rpc-bradbury.genlayer.com`)
- **Deployed contract:** [`0x92d666EC2C1bA1f1506686Be141367c69dbffc92`](https://explorer-bradbury.genlayer.com/address/0x92d666EC2C1bA1f1506686Be141367c69dbffc92)
- **Source:** [`contracts/GenClashArena.py`](./contracts/GenClashArena.py) and [`index.html`](./index.html)

---

## 1. Intelligent Contract (Python on GenVM)

| GenLayer docs requirement                                          | Implementation in `contracts/GenClashArena.py` |
| ------------------------------------------------------------------ | ---------------------------------------------- |
| `# { "Depends": "py-genlayer:..." }` header                        | Line 1                                         |
| `from genlayer import *`                                           | Line 22                                        |
| Contract inherits `gl.Contract`                                    | `class GenClashArena(gl.Contract)` line 41     |
| Persistent storage typed with `TreeMap`, `DynArray`, `Address`, `u256` | Lines 43–69                                |
| `@gl.public.write.payable` for paid entry                          | `pay_to_play` line 83                          |
| `@gl.public.write` for state mutations                             | `report_win` 112, `report_loss` 148, `claim_run_bonus` 166, `refresh_weekly_theme` 228 |
| `@gl.public.view` for reads                                        | Lines 261–315 (9 view methods)                 |
| Access to message context via `gl.message.sender_address` / `gl.message.value` | Lines 73, 94, 99, 118, 154, 175      |
| Explicit user errors with `gl.vm.UserError`                        | Lines 95, 120, 124, 156, 178                   |
| Native value transfer accounting                                   | `total_fees_collected` line 107                |

## 2. Optimistic Democracy + Equivalence Principle (AI in critical path)

The contract uses GenVM non-determinism (LLM in consensus) in **three** places.
Crucially, **`report_win` itself is AI-judged** — every single level-up
transaction triggers an LLM call inside Optimistic Democracy consensus. This
puts AI in the game's critical path, not in an optional showcase.

| Pattern from docs                                                  | Implementation                                 |
| ------------------------------------------------------------------ | ---------------------------------------------- |
| Leader proposes an LLM result via `gl.nondet.exec_prompt(...)`     | `leader_fn` in `report_win` (~line 171), `claim_run_bonus`, and `refresh_weekly_theme` |
| Validators independently run the LLM and verify agreement (Equivalence Principle) | `validator_fn` re-runs `leader_fn` and compares the verdict |
| Combined under `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`  | `report_win`, `claim_run_bonus`, `refresh_weekly_theme` |
| JSON-structured LLM output (`response_format="json"`)              | All three nondet calls                         |
| Validator returns `bool` to accept/reject leader result            | All three `validator_fn`s                      |
| Hard pre-checks before invoking the LLM (cheap, deterministic)     | `report_win` validates `score == 3`, opponent score `< 3`, `5s ≤ duration ≤ 1h` before paying for the LLM call |
| Contract reverts via `gl.vm.UserError` if AI rejects               | `report_win` raises if `verdict["valid"] is false` |

**What this means for the reviewer:** every `report_win` tx in the explorer is
proof of AI-in-consensus. Click any one, and you will see the LLM prompt and
verdict in the execution receipt, plus the validator votes.

## 3. Frontend SDK usage (`genlayer-js`)

| Docs example                                                       | Implementation in `index.html`                 |
| ------------------------------------------------------------------ | ---------------------------------------------- |
| `import { createClient } from 'genlayer-js'`                       | Line 832                                       |
| `import { testnetBradbury } from 'genlayer-js/chains'`             | Line 833                                       |
| `import { TransactionStatus } from 'genlayer-js/types'`            | Line 834                                       |
| `createClient({ chain, account, provider })` with vanilla EIP-1193 | Lines 897–901 — passes `window.ethereum`, no MetaMask Snap dependency, works with MetaMask / Rabby / Coinbase Wallet / Frame / Trust |
| `client.writeContract({ address, functionName, args, value })`     | `payToPlay` line 999, `reportWin` ~1020, `reportLoss` ~1042 |
| `client.readContract({ ... })`                                     | `fetchCurrentLevel`, `fetchLeaderboard` (see below in same script tag) |
| `client.getTransaction({ hash })` for live monitoring              | `waitForAccepted` line 975 — polls every 3s, surfaces live status (`PENDING → PROPOSING → COMMITTING → REVEALING → ACCEPTED`) to the player |
| Tx lifecycle as per [docs §Transaction Lifecycle](https://docs.genlayer.com) | Implemented exactly, both happy path and `CANCELED`/`UNDETERMINED`/`LEADER_TIMEOUT`/`VALIDATORS_TIMEOUT` failure handling lines 960–993 |

## 4. Game flow → On-chain state machine

```
        ┌────────────────────────────────────────────────────────────┐
        │                                                            │
        ▼                                                            │
[Connect wallet] ─► pay_to_play() ────► play match ──► report_win() ─┘
                    (payable, 0.0001 GEN)                  │
                                                           ▼
                                                       report_loss()
                                                       (resets to L1)
```

- **Per-level fee** (0.0001 GEN) — discourages spam, finances the contract
- **Loss = reset to L1** — keeps progression meaningful
- **Highest level** persisted independently → real on-chain leaderboard
- **Strict ACCEPTED gating**: gameplay does **not** start until validators
  agree the fee was paid. Implemented in `payToPlay` → `waitForAccepted`
  (lines 996–1011).

## 5. Proof points the team can click on

Every on-chain action in this app is publicly verifiable:

- Account used during development:
  [`0x0f5BC1369677EE317F44F5E4d878D1bf6e2C87Fb`](https://explorer-bradbury.genlayer.com/address/0x0f5BC1369677EE317F44F5E4d878D1bf6e2C87Fb)
  → look at the `Transactions` tab: every entry is a `CONTRACT_CALL` to our
  contract `0x92d6…ffc92` with function `pay_to_play` / `report_win` /
  `report_loss`, value `0.0001 GEN`, nonce-ordered.
- Contract storage is observable via the `get_leaderboard`, `get_current_level`,
  `get_highest_level`, `get_xp` view methods.

## 6. Known network-side behaviour we cannot control

During testing on **2026-05-11**, Bradbury validators were running with a
significant backlog: legitimate transactions remained in `PENDING` for 15–25
minutes before advancing to `PROPOSING`/`COMMITTING`. Because Ethereum-style
RPCs require strict per-account nonce ordering, a single stuck PENDING tx
blocks every subsequent tx from the same EOA.

Our frontend:

- Surfaces this transparently — the live status counter on the start screen
  shows the player exactly which on-chain stage they are stuck on, with a
  clickable explorer link.
- Fails fast on consensus-level failures (`CANCELED`, `UNDETERMINED`,
  `LEADER_TIMEOUT`, `VALIDATORS_TIMEOUT`).
- Times out gracefully after 25 min with a clear "tx may still finalize"
  message instead of silently failing.

If the GenLayer team can confirm the activator/validator state on Bradbury,
this app will exercise the full consensus pipeline as designed.

## 7. Reproduction steps for reviewers

```bash
# Clone
git clone https://github.com/delreyir/GenClash-Arena
cd GenClash-Arena

# Inspect the contract
cat contracts/GenClashArena.py

# Inspect the on-chain integration block
sed -n '820,1130p' index.html
```

Or just open <https://gen-clash-arena.vercel.app> in a browser with any
EIP-1193 wallet (MetaMask / Rabby / Coinbase Wallet), grab some Bradbury GEN
from the faucet, and click **Start Match**.

---

*Built with `py-genlayer`, `genlayer-js`, GenVM and Optimistic Democracy.*
