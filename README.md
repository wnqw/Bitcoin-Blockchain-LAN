# Bitcoin Blockchain with LAN

A minimal Bitcoin blockchain with proof-of-work mining, ASCII visualization, and LAN networking. Zero dependencies — Python 3.10+ stdlib only!

## Offline Mode

### Interactive (add your own transactions)

```bash
python blockchain.py
python blockchain.py --name Alice    # custom miner name
```

```
[Alice] > tx Alice Bob 2.5
  Transaction queued for block #1
[Alice] > tx Bob Charlie 1.0
  Transaction queued for block #1
[Alice] > mine
  ⛏  Mining block #1 (difficulty=4)... found nonce=69732 in 0.07s
  Block #1 mined! Hash: 4c2af380a1b2c3d4...
[Alice] > chain
  (shows full ASCII chain visualization)
[Alice] > balance Alice
  Alice: 3.7500 BTC
[Alice] > pending
  No pending transactions
[Alice] > validate
  Chain integrity: ✓ VALID
```

### Offline hardcoded demo

```bash
python blockchain.py --demo
```

## Start a Network Node

```bash
python node.py --port 9000 --name Alice
```

### CLI Commands

```
tx <sender> <recipient> <amount>  — Submit a transaction
mine                              — Mine pending transactions
chain                             — Show ASCII chain visualization
balance <address>                 — Check wallet balance
peers                             — List connected peers
addpeer <host:port>               — Register a peer node
sync                              — Pull longest chain from peers
pending                           — Show pending transactions
help                              — Show this menu
quit                              — Shutdown node
```

## LAN Setup

### 1. Find your IP

```bash
ipconfig getifaddr en0        # macOS
hostname -I                   # Linux
```

### 2. Start nodes on each machine

```bash
# Machine A
python node.py --port 9000 --name Alice

# Machine B
python node.py --port 9000 --name Bob

# Machine C...
```

### 3. Connect peers (bidirectional — only one side needs to run this)

```
addpeer 192.168.x.x:9000
```

### 4. Transact and mine

```
tx Alice Bob 2.5
tx Bob Charlie 1.0
mine
```

Transactions broadcast to all peers automatically. When someone mines, all peers sync the new chain.

## HTTP API

Anyone on the LAN can interact without the CLI:

```bash
# Submit a transaction
curl -X POST http://192.168.x.x:9000/transactions/new \
  -H "Content-Type: application/json" \
  -d '{"sender":"Dave","recipient":"Alice","amount":0.5}'

# Mine pending transactions
curl -X POST http://192.168.x.x:9000/mine

# View the chain (ASCII art)
curl http://192.168.x.x:9000/visualize

# Check a balance
curl http://192.168.x.x:9000/balance/Dave

# See pending transactions
curl http://192.168.x.x:9000/pending
```

### All Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| GET | `/chain` | Full chain as JSON |
| GET | `/visualize` | ASCII chain art |
| GET | `/balance/<name>` | Wallet balance |
| GET | `/pending` | Queued transactions |
| GET | `/peers` | Connected nodes |
| POST | `/transactions/new` | Submit a transaction |
| POST | `/mine` | Mine a block |
| POST | `/peers/register` | Add a peer |
| POST | `/consensus` | Sync longest chain |

## Example LAN Use Cases

### Office payment tracker

Three coworkers split lunch costs on the office network:

```bash
# Alice's machine (192.168.1.10)
python node.py --port 9000 --name Alice

# Bob's machine (192.168.1.11)
python node.py --port 9000 --name Bob

# Charlie's machine (192.168.1.12)
python node.py --port 9000 --name Charlie
```

```
# Alice connects everyone
[Alice] > addpeer 192.168.1.11:9000
[Alice] > addpeer 192.168.1.12:9000

# Bob paid $30 for lunch, Alice and Charlie owe him
[Bob] > tx Alice Bob 10
[Bob] > tx Charlie Bob 10
[Bob] > mine

# Everyone's chain updates automatically
[Charlie] > balance Bob
  Bob: 26.2500 BTC
[Charlie] > chain
  (all 3 machines show the same chain)
```

### Multi-miner competition

Run several nodes and race to mine blocks — whoever mines first gets the 6.25 BTC reward:

```bash
# Terminal 1
python node.py --port 9000 --name Miner1

# Terminal 2
python node.py --port 9001 --name Miner2

# Terminal 3
python node.py --port 9002 --name Miner3
```

```
# Connect all peers
[Miner1] > addpeer localhost:9001
[Miner1] > addpeer localhost:9002

# Someone adds a transaction
[Miner1] > tx Alice Bob 3.0

# All miners race to mine
[Miner1] > mine
[Miner2] > mine    # if Miner1 was faster, sync will adopt their chain
[Miner2] > sync
[Miner2] > balance Miner1
  Miner1: 6.2500 BTC
```

## LAN Mode Workflow: 

```
tx submitted
    │
    ▼
pending_transactions[]
    │
  mine
    │
    ├─ coinbase prepended
    ├─ proof-of-work loop (find nonce)
    ├─ Block created + SHA-256 hashed
    └─ appended to chain
              │
          LAN sync
              │
    peers replace_chain()
              │
          balance query
              │
    replay all txs from chain
```