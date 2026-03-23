"""
A minimal Bitcoin-style blockchain with proof-of-work mining and ASCII visualization.

Usage:
    python blockchain.py
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field


@dataclass
class Transaction:
    sender: str
    recipient: str
    amount: float

    def to_dict(self) -> dict:
        return {"sender": self.sender, "recipient": self.recipient, "amount": self.amount}


@dataclass
class Block:
    index: int
    timestamp: float
    transactions: list[Transaction]
    proof: int
    previous_hash: str
    hash: str = field(init=False, default="")

    def __post_init__(self):
        self.hash = self.compute_hash()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "proof": self.proof,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
        }

    def compute_hash(self) -> str:
        block_data = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "transactions": [tx.to_dict() for tx in self.transactions],
            "proof": self.proof,
            "previous_hash": self.previous_hash,
        }, sort_keys=True)
        return hashlib.sha256(block_data.encode()).hexdigest()


class Blockchain:
    DIFFICULTY = 4  # number of leading zeros required
    MINING_REWARD = 6.25  # BTC reward per block (current era)

    def __init__(self, data_dir: str = ""):
        self.chain: list[Block] = []
        self.pending_transactions: list[Transaction] = []
        self._data_file = os.path.join(data_dir, "chain.json") if data_dir else ""
        if not self._load_from_disk():
            self._create_genesis_block()

    def _create_genesis_block(self):
        genesis = Block(
            index=0,
            timestamp=time.time(),
            transactions=[],
            proof=0,
            previous_hash="0" * 64,
        )
        self.chain.append(genesis)

    @property
    def last_block(self) -> Block:
        return self.chain[-1]

    def add_transaction(self, sender: str, recipient: str, amount: float) -> int:
        self.pending_transactions.append(Transaction(sender, recipient, amount))
        return self.last_block.index + 1

    def proof_of_work(self, previous_proof: int) -> int:
        """Find a nonce such that hash(previous_proof, nonce) has DIFFICULTY leading zeros."""
        proof = 0
        target = "0" * self.DIFFICULTY
        while True:
            guess = f"{previous_proof}{proof}".encode()
            guess_hash = hashlib.sha256(guess).hexdigest()
            if guess_hash[:self.DIFFICULTY] == target:
                return proof
            proof += 1

    def mine_pending_transactions(self, miner_address: str) -> Block:
        """Mine a new block with all pending transactions + coinbase reward."""
        self.pending_transactions.insert(
            0, Transaction(sender="COINBASE", recipient=miner_address, amount=self.MINING_REWARD)
        )

        previous_block = self.last_block
        print(f"\n  ⛏  Mining block #{previous_block.index + 1} (difficulty={self.DIFFICULTY})...", end=" ", flush=True)
        start = time.time()
        proof = self.proof_of_work(previous_block.proof)
        elapsed = time.time() - start
        print(f"found nonce={proof} in {elapsed:.2f}s")

        block = Block(
            index=previous_block.index + 1,
            timestamp=time.time(),
            transactions=list(self.pending_transactions),
            proof=proof,
            previous_hash=previous_block.hash,
        )
        self.pending_transactions.clear()
        self.chain.append(block)
        self._save_to_disk()
        return block

    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]
            if current.hash != current.compute_hash():
                return False
            if current.previous_hash != previous.hash:
                return False
        return True

    def to_dict(self) -> dict:
        return {
            "chain": [block.to_dict() for block in self.chain],
            "length": len(self.chain),
        }

    def replace_chain(self, chain_data: list[dict]) -> bool:
        """Replace chain with chain_data if it's longer and valid. Returns True if replaced."""
        if len(chain_data) <= len(self.chain):
            return False

        new_chain = []
        for block_data in chain_data:
            txs = [Transaction(**tx) for tx in block_data["transactions"]]
            block = Block(
                index=block_data["index"],
                timestamp=block_data["timestamp"],
                transactions=txs,
                proof=block_data["proof"],
                previous_hash=block_data["previous_hash"],
            )
            if block.hash != block_data["hash"]:
                return False
            new_chain.append(block)

        # Validate linkage
        for i in range(1, len(new_chain)):
            if new_chain[i].previous_hash != new_chain[i - 1].hash:
                return False

        # Remove pending transactions that are already confirmed in the new chain
        confirmed = set()
        for block in new_chain:
            for tx in block.transactions:
                if tx.sender != "COINBASE":
                    confirmed.add((tx.sender, tx.recipient, tx.amount))
        self.pending_transactions = [
            tx for tx in self.pending_transactions
            if (tx.sender, tx.recipient, tx.amount) not in confirmed
        ]

        self.chain = new_chain
        self._save_to_disk()
        return True

    def _save_to_disk(self):
        if not self._data_file:
            return
        os.makedirs(os.path.dirname(self._data_file) or ".", exist_ok=True)
        data = {"chain": [block.to_dict() for block in self.chain]}
        tmp = self._data_file + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, self._data_file)

    def _load_from_disk(self) -> bool:
        if not self._data_file or not os.path.exists(self._data_file):
            return False
        try:
            with open(self._data_file) as f:
                data = json.load(f)
            for block_data in data["chain"]:
                txs = [Transaction(**tx) for tx in block_data["transactions"]]
                block = Block(
                    index=block_data["index"],
                    timestamp=block_data["timestamp"],
                    transactions=txs,
                    proof=block_data["proof"],
                    previous_hash=block_data["previous_hash"],
                )
                if block.hash != block_data["hash"]:
                    return False
                self.chain.append(block)
            return len(self.chain) > 0
        except (json.JSONDecodeError, KeyError):
            return False

    def get_balance(self, address: str) -> float:
        balance = 0.0
        for block in self.chain:
            for tx in block.transactions:
                if tx.sender == address:
                    balance -= tx.amount
                if tx.recipient == address:
                    balance += tx.amount
        return balance


# ─── ASCII Visualization ────────────────────────────────────────────────

def short_hash(h: str) -> str:
    return h[:8] + "..." + h[-4:]


def format_block_box(block: Block, width: int = 52) -> list[str]:
    """Render a single block as an ASCII box."""
    lines = []
    border = "+" + "─" * (width - 2) + "+"
    empty = "│" + " " * (width - 2) + "│"

    def row(text: str) -> str:
        return "│ " + text.ljust(width - 4) + " │"

    lines.append(border)
    if block.index == 0:
        lines.append(row("★  GENESIS BLOCK"))
    else:
        lines.append(row(f"BLOCK #{block.index}"))
    lines.append("│" + "─" * (width - 2) + "│")
    lines.append(row(f"Hash:      {short_hash(block.hash)}"))
    lines.append(row(f"Prev Hash: {short_hash(block.previous_hash)}"))
    lines.append(row(f"Nonce:     {block.proof}"))
    lines.append(row(f"Time:      {time.strftime('%H:%M:%S', time.localtime(block.timestamp))}"))
    lines.append(row(f"Tx Count:  {len(block.transactions)}"))

    if block.transactions:
        lines.append("│" + "─" * (width - 2) + "│")
        for tx in block.transactions:
            sender = tx.sender[:10]
            recip = tx.recipient[:10]
            label = f"{sender} → {recip}: {tx.amount} BTC"
            lines.append(row(label))

    lines.append(border)
    return lines


def print_chain(blockchain: Blockchain):
    """Print the full blockchain as linked ASCII blocks."""
    width = 52
    chain_link = [
        " " * (width // 2 - 1) + "│",
        " " * (width // 2 - 1) + "│",
        " " * (width // 2 - 4) + "╔══╧══╗",
        " " * (width // 2 - 4) + "║CHAIN║",
        " " * (width // 2 - 4) + "╚══╤══╝",
        " " * (width // 2 - 1) + "│",
        " " * (width // 2 - 1) + "▼",
    ]

    print()
    print("=" * 60)
    print("  BITCOIN BLOCKCHAIN VISUALIZER")
    print("=" * 60)

    for i, block in enumerate(blockchain.chain):
        box_lines = format_block_box(block, width)
        for line in box_lines:
            print("    " + line)

        if i < len(blockchain.chain) - 1:
            for link_line in chain_link:
                print("    " + link_line)

    print()
    valid = blockchain.is_chain_valid()
    status = "✓ VALID" if valid else "✗ INVALID"
    print(f"  Chain integrity: {status}")
    print(f"  Total blocks:    {len(blockchain.chain)}")
    print("=" * 60)


# ─── Demo ────────────────────────────────────────────────────────────────

def run_demo():
    bc = Blockchain()
    miner = "Satoshi"

    print("\n" + "=" * 60)
    print("  BITCOIN BLOCKCHAIN DEMO")
    print("=" * 60)

    # -- Round 1 --
    bc.add_transaction("Alice", "Bob", 1.5)
    bc.add_transaction("Bob", "Charlie", 0.7)
    bc.mine_pending_transactions(miner)

    # -- Round 2 --
    bc.add_transaction("Charlie", "Alice", 2.0)
    bc.add_transaction("Alice", "Dave", 0.3)
    bc.add_transaction("Dave", "Bob", 1.0)
    bc.mine_pending_transactions(miner)

    # -- Round 3 --
    bc.add_transaction("Bob", "Alice", 0.5)
    bc.mine_pending_transactions(miner)

    # -- Visualize --
    print_chain(bc)

    # -- Balances --
    addresses = ["Satoshi", "Alice", "Bob", "Charlie", "Dave"]
    print("\n  WALLET BALANCES")
    print("  " + "─" * 30)
    for addr in addresses:
        bal = bc.get_balance(addr)
        print(f"  {addr:<12} {bal:>10.4f} BTC")
    print()

    # -- Tamper test --
    print("  TAMPER TEST")
    print("  " + "─" * 30)
    print("  Modifying block #1 data...")
    bc.chain[1].transactions[0] = Transaction("HACKER", "HACKER", 9999)
    valid = bc.is_chain_valid()
    print(f"  Chain valid after tampering? {'Yes' if valid else 'No — tampering detected!'}")
    print()


def run_interactive():
    """Interactive offline mode — add transactions, mine, and explore."""
    import argparse
    parser = argparse.ArgumentParser(description="Bitcoin Blockchain (offline)")
    parser.add_argument("--demo", action="store_true", help="Run the hardcoded demo")
    parser.add_argument("--name", "-n", type=str, default="Satoshi", help="Miner name")
    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    bc = Blockchain()
    miner = args.name

    print("\n" + "=" * 58)
    print(f"  ⛓  BITCOIN BLOCKCHAIN (offline)")
    print(f"  ⛏  Miner: {miner}")
    print("=" * 58)

    help_text = """
  Commands:
    tx <sender> <recipient> <amount>  — Queue a transaction
    mine                              — Mine pending transactions
    chain                             — Show ASCII chain
    balance <address>                 — Check wallet balance
    pending                           — Show pending transactions
    validate                          — Check chain integrity
    help                              — Show this menu
    quit                              — Exit
"""
    print(help_text)

    while True:
        try:
            raw = input(f"[{miner}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()

        if cmd == "help":
            print(help_text)

        elif cmd == "tx":
            if len(parts) != 4:
                print("  Usage: tx <sender> <recipient> <amount>")
                continue
            try:
                amount = float(parts[3])
            except ValueError:
                print("  Amount must be a number")
                continue
            idx = bc.add_transaction(parts[1], parts[2], amount)
            print(f"  Transaction queued for block #{idx}")

        elif cmd == "mine":
            if not bc.pending_transactions:
                print("  No pending transactions to mine")
                continue
            block = bc.mine_pending_transactions(miner)
            print(f"  Block #{block.index} mined! Hash: {block.hash[:16]}...")

        elif cmd == "chain":
            print_chain(bc)

        elif cmd == "balance":
            if len(parts) != 2:
                print("  Usage: balance <address>")
                continue
            bal = bc.get_balance(parts[1])
            print(f"  {parts[1]}: {bal:.4f} BTC")

        elif cmd == "pending":
            if not bc.pending_transactions:
                print("  No pending transactions")
            else:
                for tx in bc.pending_transactions:
                    print(f"  {tx.sender} → {tx.recipient}: {tx.amount} BTC")

        elif cmd == "validate":
            valid = bc.is_chain_valid()
            print(f"  Chain integrity: {'✓ VALID' if valid else '✗ INVALID'}")

        elif cmd == "quit":
            break

        else:
            print(f"  Unknown command: {cmd}. Type 'help' for options.")


if __name__ == "__main__":
    run_interactive()
