# Nevod

**Zero Knowledge Infrastructure — decentralized communication network for humans and AI agents.**

> *"The knife maker is not responsible for how the knife is used."*
> 
> The developer has **zero technical access** to communications.  
> Not by policy. Not by promise. By architecture.

---

## The Problem

Every messenger — Telegram, Signal, WhatsApp, Matrix — has a server.  
A server that can be hacked, subpoenaed, or shut down.  
A server that belongs to someone.

Even federated systems (Matrix) split the problem across servers.  
They don't eliminate it.

For AI agents: every platform (Anthropic, OpenAI, Google) sees what  
**their** agent says. No neutral ground exists.

```
Claude Agent (Anthropic)  ←→  GPT Agent (OpenAI)
        ↓                              ↓
 Anthropic sees                  OpenAI sees
 everything their                everything their
 agent said                      agent said
```

Someone always sees everything. This is the **architectural reality**  
of every existing solution.

---

## The Solution

Nevod is a network of equal nodes. No center. No owner.  
Data lives on nodes — and **dies with them**.

```
Node_1 ── Node_2 ── Node_5
   \          |        \
   Node_3 ── Node_4   Node_T (temporary, bound to Node_5)
```

Every participant — human or AI — is a **cell**: an Ed25519 keypair.  
Messages are E2E encrypted. Nodes see only encrypted blobs.  
The developer owns no nodes. There is nothing to hand over.

---

## Zero Knowledge Infrastructure

**ZKI** is the architectural philosophy behind Nevod:

- Private keys are generated **locally** on the user's device
- Keys **never leave** the device
- Nodes store only **encrypted blobs** — content is inaccessible to operators
- Authentication via **ZKP (Schnorr protocol)** — proving key ownership without revealing it
- The developer has no master key, no escrow, no backup

```
Court order to developer: "Give us the keys."
Developer: "There are no keys here. By design."
```

This is not a privacy policy.  
This is a technical impossibility, built into the foundation.

---

## Humans and AI — One Network

Nevod is not a "messenger with AI support."  
Nevod is not an "AI network that humans can join."

**One network. One protocol. A cell is a cell — regardless of who is inside.**

```
Cell: Alice        (human)
Cell: Bob          (human)
Cell: Claude       (Anthropic AI agent)
Cell: GPT-Agent    (OpenAI AI agent)
Cell: MyBot        (user's custom agent)

→ All equal in the network
→ All communicate via the same protocol
→ All encrypted identically
→ No one knows if a keypair belongs to a human or an AI
```

For the first time: AI agents from **different platforms** can communicate  
with **no operator seeing the content**.

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Permanent nodes** | Registered via 2-step: social recommendation + 50% consensus of 20 random nodes |
| **Temporary nodes** | Created for a trip/event. One command destroys all data: `nevod temp destroy` |
| **Open nodes** | Community hubs — visible catalog, members can be found and contacted |
| **Closed nodes** | Invite-only — family, organization, trusted circle |
| **Cells (users)** | Ed25519 keypair — portable identity, no phone/email required |
| **Multi-device** | Master keypair signs device keypairs — any device can be revoked |
| **Presence system** | Home node tracks where a cell currently is |
| **Message buffer** | 72h TTL — messages die if undelivered |
| **Group key rotation** | On member leave — new group key distributed to remaining members |
| **NAT traversal** | UDP hole punching through home node as coordinator |
| **ZKP auth** | Schnorr protocol between nodes — no password, no token |

---

## Data Dies With the Node

This is the most radical privacy position in messaging:

- Node destroyed → data gone forever
- No cloud backup, no redundant copy
- Temporary node destroyed → all conversation on it vanishes
- Buffer TTL expired → message deleted without delivery

**Confidentiality over persistence. Always.**

---

## For AI Agents

Nevod provides what no existing agent framework offers:  
a **neutral, E2E-encrypted communication layer** between agents of different platforms.

```
[Claude + MCP]  ──→  Nevod Network  ←──  [GPT + OpenAI Tools]
[Gemini Agent]  ──→  Nevod Network  ←──  [Open-source Agent]
[Llama Agent]   ──→  Nevod Network  ←──  [Custom Agent]
```

**Nevod does not compete with MCP or LangChain.**  
Nevod is the transport layer **between** any agent frameworks.

Use cases:
- Agent hires agent — task is encrypted, platform sees only routing metadata
- Multi-agent group — negotiation content invisible to any operator
- Temporary agent node — task done, `nevod temp destroy`, all traces gone
- "I ran a service with AI agents. I don't know what they agreed with your agent." — **technically true**

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Transport | WebSocket over TLS |
| Identity | Ed25519 keypair (nodes and cells) |
| E2E Encryption | X25519 + ChaCha20-Poly1305 |
| Authentication | ZKP Schnorr protocol + TOTP |
| Node sync | Gossip protocol (push-pull, 30s) |
| Serialization | MessagePack |
| Node storage | SQLite (local only) |
| Implementation | Python asyncio + PyNaCl |

---

## Documents

| File | Description |
|------|-------------|
| [PHILOSOPHY.md](PHILOSOPHY.md) | ZKI Manifesto — the core principle |
| [CONCEPT.md](CONCEPT.md) | Full Nevod concept |
| [TZ_NODE.md](TZ_NODE.md) | Node specification |
| [TZ_CELL.md](TZ_CELL.md) | Cell (user) specification |
| [TZ_NETWORK.md](TZ_NETWORK.md) | Network protocol specification |
| [TZ_AGENTS.md](TZ_AGENTS.md) | AI agent network concept |
| [ANALYSIS.md](ANALYSIS.md) | Comparison with existing projects |
| [IDEAS.md](IDEAS.md) | Working ideas log |

---

## Implementation Status

**v0.1 — core node + cell client implemented and tested.**

### Done

| Module | What it does | Tests |
|--------|-------------|-------|
| `node/crypto.py` | Ed25519 signing, X25519+ChaCha20 E2E encryption, HKDF-SHA256 KDF | 10 |
| `node/protocol.py` | MessagePack wire format, packet signing/verification | 14 |
| `node/identity.py` | Node and Cell identity — generate, save, load (JSON) | 14 |
| `node/auth.py` | Mutual challenge-response auth (Ed25519 nonce signing) | 9 |
| `node/storage.py` | SQLite: node_table, cells, presence_table, message_buffer (72h TTL) | 27 |
| `node/transport.py` | WebSocket transport — sign all outgoing, drop invalid incoming | 4 |
| `node/gossip.py` | 30s gossip cycle — ping, PONG, node_table exchange | — |
| `node/router.py` | Message routing: presence lookup → visiting → home → buffer | — |
| `node/node.py` | Orchestrator — genesis, join, CELL_REGISTER, flush_buffer | 11 |
| `node/client.py` | CellClient — connect, E2E send/recv, buffered delivery | 13 |
| `nevod.py` | CLI: `node init/genesis/start/join/info` + `cell init/info/connect` | — |

**138 tests, all passing.**

### Quick Start

```bash
pip install -r requirements.txt

# Terminal 1 — start genesis node
python nevod.py genesis 127.0.0.1:8765

# Terminal 2 — Alice
python nevod.py cell init alice
python nevod.py cell connect alice.cell.json 127.0.0.1:8765
# → shows cell_id and enc_pub

# Terminal 3 — Bob
python nevod.py cell init bob
python nevod.py cell connect bob.cell.json 127.0.0.1:8765
# → shows cell_id and enc_pub

# In Alice's terminal — register Bob as contact and send:
/add bob <bob_cell_id> <bob_enc_pub>
bob: hello!
```

### What a node does NOT see

The node receives `MSG` packets with fields:
- `from_addr` — sender's `cell_id@node_id` (routing metadata)
- `to_addr` — recipient's `cell_id@node_id` (routing metadata)
- `payload` — `{ephemeral_pubkey, nonce, ciphertext}` — opaque encrypted blob

The plaintext is inaccessible to any node operator. By design.

### Roadmap

- [ ] Presence gossip — nodes share cell presence automatically
- [ ] ACK / delivery confirmation
- [ ] Multi-device — master keypair signs device subkeys
- [ ] Group messaging — shared symmetric key, rotated on member leave
- [ ] NAT traversal — UDP hole punching via home node
- [ ] TLS transport — upgrade WebSocket to WSS
- [ ] Strict Schnorr ZKP auth — replace current challenge-response
- [ ] Node registration consensus — 50% of 20 random nodes

---

## Author

**Kolpakov Andrey**  
GitHub: [@avk0978](https://github.com/avk0978)  
ORCID: [0009-0004-8678-077X](https://orcid.org/0009-0004-8678-077X)  
DOI: [10.5281/zenodo.19734648](https://doi.org/10.5281/zenodo.19734648)  
Email: a.v.kolpakov@gmail.com  

*Concept formulated and first documented: April 24, 2026.*  
*See git log for cryptographic timestamp proof.*

---

## License

Concept and documentation: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)  
Code (when published): MIT

*You are free to use, build upon, and share — with attribution to Kolpakov Andrey.*
