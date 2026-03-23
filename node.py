"""
Blockchain network node — run on your LAN.

Usage:
    python node.py --port 5000 --name Alice
    python node.py --port 5001 --name Bob

Then on Alice's CLI:  addpeer localhost:5001
"""

import argparse
import io
import json
import threading
import urllib.request
import urllib.error
from contextlib import redirect_stdout
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer

from blockchain import Blockchain, Transaction, print_chain


# ─── Shared Node State ──────────────────────────────────────────────────

class NodeState:
    def __init__(self, name: str, port: int):
        self.name = name
        self.port = port
        self.data_dir = f"data_{name}"
        self.blockchain = Blockchain(data_dir=self.data_dir)
        self.peers: set[str] = set()  # "host:port" strings
        self.lock = threading.Lock()


state: NodeState  # set in main()


# ─── Peer Communication ─────────────────────────────────────────────────

def broadcast_transaction(tx_data: dict):
    """Fire-and-forget POST to all peers."""
    payload = json.dumps({**tx_data, "broadcast": False}).encode()
    for peer in list(state.peers):
        def _send(p=peer):
            try:
                req = urllib.request.Request(
                    f"http://{p}/transactions/new",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=3)
            except Exception:
                pass
        threading.Thread(target=_send, daemon=True).start()


def notify_peers_to_sync():
    """Tell all peers to run consensus after we mined a block."""
    for peer in list(state.peers):
        def _notify(p=peer):
            try:
                req = urllib.request.Request(
                    f"http://{p}/consensus",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception:
                pass
        threading.Thread(target=_notify, daemon=True).start()


def resolve_conflicts() -> bool:
    """Pull chains from all peers, adopt the longest valid one."""
    replaced = False
    for peer in list(state.peers):
        try:
            resp = urllib.request.urlopen(f"http://{peer}/chain", timeout=5)
            data = json.loads(resp.read().decode())
            with state.lock:
                if state.blockchain.replace_chain(data["chain"]):
                    replaced = True
        except Exception:
            pass
    return replaced


def register_peer_bidirectional(peer_address: str):
    """Register a peer, and tell it about us."""
    state.peers.add(peer_address)
    # Tell the remote peer about us
    def _register():
        try:
            payload = json.dumps({"peer": f"localhost:{state.port}", "broadcast": False}).encode()
            req = urllib.request.Request(
                f"http://{peer_address}/peers/register",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass
    threading.Thread(target=_register, daemon=True).start()


# ─── HTTP Handler ────────────────────────────────────────────────────────

class BlockchainHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Suppress default HTTP logs to keep CLI clean
        pass

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, status: int = 200):
        body = text.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode())

    # ── GET routes ───────────────────────────────────────────────────

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/chain":
            with state.lock:
                data = state.blockchain.to_dict()
            self._send_json(data)

        elif path == "/pending":
            with state.lock:
                txs = [tx.to_dict() for tx in state.blockchain.pending_transactions]
            self._send_json({"transactions": txs, "count": len(txs)})

        elif path == "/peers":
            self._send_json({"peers": sorted(state.peers)})

        elif path == "/visualize":
            buf = io.StringIO()
            with state.lock:
                with redirect_stdout(buf):
                    print_chain(state.blockchain)
            self._send_text(buf.getvalue())

        elif path.startswith("/balance/"):
            address = path.split("/balance/", 1)[1]
            if not address:
                self._send_json({"error": "address required"}, 400)
                return
            with state.lock:
                balance = state.blockchain.get_balance(address)
            self._send_json({"address": address, "balance": balance})

        else:
            self._send_json({"error": "not found"}, 404)

    # ── POST routes ──────────────────────────────────────────────────

    def do_POST(self):
        path = self.path.rstrip("/")

        if path == "/transactions/new":
            data = self._read_json()
            required = ("sender", "recipient", "amount")
            if not all(k in data for k in required):
                self._send_json({"error": f"missing fields: {required}"}, 400)
                return
            with state.lock:
                idx = state.blockchain.add_transaction(
                    data["sender"], data["recipient"], float(data["amount"])
                )
            self._send_json({"message": f"Transaction queued for block #{idx}", "block_index": idx})
            # Broadcast to peers unless this is already a broadcast
            if data.get("broadcast", True):
                broadcast_transaction({"sender": data["sender"], "recipient": data["recipient"], "amount": data["amount"]})

        elif path == "/mine":
            with state.lock:
                if not state.blockchain.pending_transactions:
                    self._send_json({"message": "No pending transactions to mine"})
                    return
                block = state.blockchain.mine_pending_transactions(state.name)
            self._send_json({"message": f"Block #{block.index} mined!", "block": block.to_dict()})
            notify_peers_to_sync()

        elif path == "/peers/register":
            data = self._read_json()
            peer = data.get("peer")
            if not peer:
                self._send_json({"error": "provide 'peer' as host:port"}, 400)
                return
            already_known = peer in state.peers
            state.peers.add(peer)
            self._send_json({"message": f"Peer {peer} registered", "peers": sorted(state.peers)})
            # Reciprocate if this isn't already a reciprocal call
            if not already_known and data.get("broadcast", True):
                register_peer_bidirectional(peer)

        elif path == "/consensus":
            replaced = resolve_conflicts()
            with state.lock:
                length = len(state.blockchain.chain)
            if replaced:
                self._send_json({"message": "Chain replaced", "chain_length": length})
            else:
                self._send_json({"message": "Chain is authoritative", "chain_length": length})

        else:
            self._send_json({"error": "not found"}, 404)


# ─── CLI ─────────────────────────────────────────────────────────────────

HELP_TEXT = """
  Commands:
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
"""


def cli_loop():
    print(HELP_TEXT)
    while True:
        try:
            raw = input(f"[{state.name}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nShutting down...")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()

        if cmd == "help":
            print(HELP_TEXT)

        elif cmd == "tx":
            if len(parts) != 4:
                print("  Usage: tx <sender> <recipient> <amount>")
                continue
            sender, recipient, amount_str = parts[1], parts[2], parts[3]
            try:
                amount = float(amount_str)
            except ValueError:
                print("  Amount must be a number")
                continue
            with state.lock:
                idx = state.blockchain.add_transaction(sender, recipient, amount)
            print(f"  Transaction queued for block #{idx}")
            broadcast_transaction({"sender": sender, "recipient": recipient, "amount": amount})

        elif cmd == "mine":
            with state.lock:
                if not state.blockchain.pending_transactions:
                    print("  No pending transactions to mine")
                    continue
                block = state.blockchain.mine_pending_transactions(state.name)
            print(f"  Block #{block.index} mined! Hash: {block.hash[:16]}...")
            notify_peers_to_sync()

        elif cmd == "chain":
            with state.lock:
                print_chain(state.blockchain)

        elif cmd == "balance":
            if len(parts) != 2:
                print("  Usage: balance <address>")
                continue
            with state.lock:
                bal = state.blockchain.get_balance(parts[1])
            print(f"  {parts[1]}: {bal:.4f} BTC")

        elif cmd == "peers":
            if not state.peers:
                print("  No peers connected")
            else:
                for p in sorted(state.peers):
                    print(f"  • {p}")

        elif cmd == "addpeer":
            if len(parts) != 2:
                print("  Usage: addpeer <host:port>")
                continue
            peer = parts[1]
            register_peer_bidirectional(peer)
            print(f"  Peer {peer} registered")

        elif cmd == "sync":
            print("  Syncing with peers...")
            replaced = resolve_conflicts()
            if replaced:
                with state.lock:
                    print(f"  Chain replaced! New length: {len(state.blockchain.chain)}")
            else:
                print("  Chain is already up to date")

        elif cmd == "pending":
            with state.lock:
                txs = state.blockchain.pending_transactions
                if not txs:
                    print("  No pending transactions")
                else:
                    for tx in txs:
                        print(f"  {tx.sender} → {tx.recipient}: {tx.amount} BTC")

        elif cmd == "quit":
            print("Shutting down...")
            break

        else:
            print(f"  Unknown command: {cmd}. Type 'help' for options.")


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    global state

    parser = argparse.ArgumentParser(description="Blockchain LAN Node")
    parser.add_argument("--port", "-p", type=int, default=9000, help="Port to listen on")
    parser.add_argument("--name", "-n", type=str, default=None, help="Miner name / node ID")
    args = parser.parse_args()

    name = args.name or f"node-{args.port}"
    state = NodeState(name, args.port)

    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer(("0.0.0.0", args.port), BlockchainHandler)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print("=" * 58)
    print(f"  ⛓  BLOCKCHAIN NODE: {name}")
    print(f"  🌐 Listening on 0.0.0.0:{args.port}")
    print(f"  📡 LAN peers can connect to <your-ip>:{args.port}")
    print("=" * 58)

    try:
        cli_loop()
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
