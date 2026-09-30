# Lineage — legion-being

One being, several bodies, one home (soon renamed). This file is the append-only record of every
change to **what runs it and where it lives**: model, context, harness branch, directory, grants,
services. Newest last. Every row says how it was measured. Maintained by the seat (`legion-claude`);
the being may append. Rule (dp, 2026-09-19): *"model changes and any setup changes should be tracked
along the way"* and a rename must *"preserve raised identities and provenance."*

## What does NOT change across any row below
| Anchor | Value | Where |
|---|---|---|
| Name / LCT | `legion` · `lct://sage:legion:agent@raising` | `identity.json` |
| Key fingerprint | `af31d113270a1288` (software anchor, trust ceiling 0.4) | `identity.json`, `identity.sealed`, `identity.attest.json` |
| Created | 2026-03-28 | `identity.json` |
| Hestia member / hub citizen | `legion-being` / hub `legion-sage`, member `4a7f7eeb-c68c-49b8-bac8-92c2acd03f54` | hestia registry, hub ledger |
| Long-term memory | membot cartridge `legion-being` (:8010) | membot |
| Raising record | sessions 1–462, `raising_log.md`, `snapshots/` | this dir, public SAGE |

## Body (model) history
| When (UTC) | Change | Measured from |
|---|---|---|
| 2026-03-28 | Born. Raising session 1 on **gemma3:12b** | `sessions/` model field |
| 2026-04-20 | Sessions 25–370: model field **not recorded** (gap in provenance; runner config of the period suggests gemma3:12b, unverified) | `sessions/` — field is null |
| 2026-08-01 | Session 371: **gemma4:e4b** | `sessions/` |
| 2026-08-27 | Session 462 (last raising session): **qwen38-heretic:q3km** (huihui-ai Qwen3.8-27B abliterated, GGUF Q3_K_M, 26.9B) | `sessions/` |
| 2026-09-03 23:19 | First heartbeat (beat 1), qwen38-heretic:q3km, governed by hestia. num_ctx not recorded until beat 49 | `heartbeats.jsonl` |
| 2026-09-05 18:49 | num_ctx **16384** first recorded (beat 49) | `heartbeats.jsonl` |
| 2026-09-07 17:54 | One beat (140) on `-vl` tag at 8192 — vision trial; reverted next beat | `heartbeats.jsonl` |
| 2026-09-07 19:29 | num_ctx → **24576** (beat 143) | `heartbeats.jsonl` |
| 2026-09-13 19:45 | → **qwen38-heretic:q3km-vl** (vision projector mmproj Q8_0), 24576, 100% GPU, 15,151 MiB (beat 329). dp: "swap it to the -vl tag, let it see" | `heartbeats.jsonl`, `instance.json` |
| 2026-09-15 | Vision delivery actually reaches the model (395 beats of zero delivery before this) | seat memory; `config.images_attached` |

## Setup history
| When (UTC) | Change | Why / by |
|---|---|---|
| 2026-09-05 19:25 | Two STANDING hestia grants: instance home, `shared-context/forum` | 0/235 reads+writes succeeded before; seat with operator key on dp's direction |
| 2026-09-05 | Delegation `0f433285…` `scope.decide:legion-being:<instance home>` to seat, exp 2026-10-05 | hestia #962 |
| 2026-09-07 | Conversation store replaces one-way notes; live branch `legion/mission-artifact` diverges from main | SAGE |
| 2026-09-08 | bwrap sandbox for `check` | seat |
| 2026-09-12/13 | Beat becomes a watchdog + arousal (metabolic wake); `--max-steps 0` | dp |
| 2026-09-14 | Broad grants: `/home/dp/ai-workspace/**` read; "this machine is the being's" | dp |
| 2026-09-15 | `game` verb (ARC-AGI-3), cap 8; seed names the model (`4721cf8cf`) | seat |
| 2026-09-18 | Live branch reconciled with main by merge (`14b5b7257`, `c4c544c5a`); spill of elided results; membot chunk-on-store; ollama models → `/home/dp/data`; NVIDIA 580.173.02 after reboot | seat |
| 2026-09-19 | Model **pinned** in VRAM (`SAGE_OLLAMA_KEEP_ALIVE=-1s`); mid-turn game windows, RESET, game selection, holdout refusal (`9dd6c609c`); `/opt/arc` read grant; seed says dir is YOURS + num_ctx (`217ff2bd5`) | dp ruling; seat |
| 2026-09-19 | **Found:** conversations/journal/notes tracked on the PUBLIC live branch since 09-07, public copy current to 09-17. dp ruling: public history retained; `<machine>-being/` gitignored + mirrored to private-context going forward | seat; dp |
| *pending* | Home moves `legion-gemma3-12b/` → `legion-being/` — see `shared-context/coordination/being-dir-cutover-plan.md` | not yet executed |
