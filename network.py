import socket
import threading
import json
import time
import sys
from typing import Dict, Tuple, Optional


class ChatNetwork:
    def __init__(self, host: str = "localhost", port: int = 5000):
        self.host = host
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.peers: Dict[Tuple[str, int], socket.socket] = {}
        self.running = False
        self.message_callback = None
        self.message_buffers: Dict[Tuple[str, int], str] = {}
        self.last_heartbeat = {}
        self.heartbeat_interval = 5
        self.connection_timeout = 15
        self.processed_messages = set()  # Track processed message IDs
        self.message_ttl = 100  # Limit size of processed messages set

    def _handle_peer(self, peer_socket: socket.socket, address: Tuple[str, int]):
        """Handle peer connection with keep-alive"""
        # Set socket options
        peer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        peer_socket.settimeout(self.connection_timeout)

        self.message_buffers[address] = ""
        self.last_heartbeat[address] = time.time()

        while self.running:
            try:
                data = peer_socket.recv(4096).decode("utf-8")
                if not data:
                    # Don't try to reconnect from handler - just break and clean up
                    break

                # Update heartbeat on any data received
                self.last_heartbeat[address] = time.time()

                # Append to message buffer
                self.message_buffers[address] += data

                # Process complete messages
                while "\n" in self.message_buffers[address]:
                    try:
                        message_raw, self.message_buffers[address] = (
                            self.message_buffers[address].split("\n", 1)
                        )
                        message = json.loads(message_raw)

                        # Check for duplicate messages
                        msg_id = f"{message.get('timestamp')}_{message.get('sender')}"
                        if msg_id in self.processed_messages:
                            continue

                        # Add to processed messages
                        self.processed_messages.add(msg_id)
                        if len(self.processed_messages) > self.message_ttl:
                            self.processed_messages.pop()

                        if self.message_callback:
                            self.message_callback(address, message)
                    except json.JSONDecodeError as e:
                        print(f"Invalid message from {address}: {e}")
                        self.message_buffers[address] = ""  # Clear buffer on error
                        continue

            except socket.timeout:
                if not self._check_connection(address):
                    break
            except Exception as e:
                print(f"Connection error with {address}: {e}")
                break  # Remove reconnection attempt from here

        self._remove_peer(address)

    def _try_reconnect(self, address: Tuple[str, int], max_attempts: int = 3) -> bool:
        """Attempt to reconnect to a peer"""
        # Prevent reconnection to self address
        if address[0] in ("localhost", "127.0.0.1") and address[1] == self.port:
            return False

        # Check if we already have a connection to this peer
        if address in self.peers and self.peers[address]:
            try:
                # Test if connection is still valid
                self.peers[address].sendall(b"")
                return True  # Connection still active
            except:
                pass  # Connection is broken, proceed with reconnection

        for _ in range(max_attempts):
            try:
                print(f"Attempting to reconnect to {address}...")
                new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                new_socket.connect(address)
                self.peers[address] = new_socket
                self.last_heartbeat[address] = time.time()
                print(f"Successfully reconnected to {address}")

                # Start handler for this peer
                thread = threading.Thread(
                    target=self._handle_peer, args=(new_socket, address)
                )
                thread.daemon = True
                thread.start()

                return True
            except Exception as e:
                print(f"Reconnection attempt failed: {e}")
                time.sleep(1)
        return False

    def _check_connection(self, address: Tuple[str, int]) -> bool:
        """Check if connection is still alive"""
        try:
            heartbeat = {"type": "heartbeat", "timestamp": time.time()}
            return self.send_to_peer(address, heartbeat)
        except:
            return False

    def send_to_peer(self, peer_address: Tuple[str, int], message: dict) -> bool:
        if peer_address not in self.peers:
            return False
        try:
            data = json.dumps(message) + "\n"
            self.peers[peer_address].send(data.encode("utf-8"))
            return True
        except Exception as e:
            print(f"Send error to {peer_address}: {e}")
            self._remove_peer(peer_address)
            return False

    def start(self, message_callback=None):
        """Start the chat network server"""
        self.message_callback = message_callback
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True

        # Start listening thread
        self.listen_thread = threading.Thread(target=self._accept_connections)
        self.listen_thread.daemon = True
        self.listen_thread.start()

        print(f"Chat server started on {self.host}:{self.port}")
        # Start heartbeat thread
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()

    def _heartbeat_loop(self):
        while self.running:
            self._send_heartbeats()
            self._check_connections()
            time.sleep(self.heartbeat_interval)

    def _send_heartbeats(self):
        heartbeat = {"type": "heartbeat", "timestamp": time.time()}
        for peer in list(self.peers.keys()):
            self.send_to_peer(peer, heartbeat)

    def _check_connections(self):
        """Check connection health for all peers"""
        current_time = time.time()
        for peer in list(self.peers.keys()):
            if (
                current_time - self.last_heartbeat.get(peer, 0)
                > self.connection_timeout
            ):
                print(f"Connection timeout for {peer}")
                self._remove_peer(peer)

    def _accept_connections(self):
        """Accept incoming peer connections"""
        while self.running:
            try:
                client_sock, address = self.server_socket.accept()
                print(f"New peer connection from {address}")
                self.peers[address] = client_sock

                # Start handler thread for this peer
                thread = threading.Thread(
                    target=self._handle_peer, args=(client_sock, address)
                )
                thread.daemon = True
                thread.start()
            except Exception as e:
                if self.running:
                    print(f"Error accepting connection: {e}")

    def connect_to_peer(self, peer_host: str, peer_port: int) -> bool:
        """Connect to a peer"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((peer_host, peer_port))
            self.peers[(peer_host, peer_port)] = sock

            # Start handler thread for this peer
            thread = threading.Thread(
                target=self._handle_peer, args=(sock, (peer_host, peer_port))
            )
            thread.daemon = True
            thread.start()
            return True
        except Exception as e:
            print(f"Failed to connect to peer {peer_host}:{peer_port}: {e}")
            return False

    def _remove_peer(self, peer_address: Tuple[str, int]) -> None:
        """Remove peer by address"""
        if peer_address in self.peers:
            self.peers[peer_address].close()
            self.peers.pop(peer_address)
            self.message_buffers.pop(peer_address, None)
            self.last_heartbeat.pop(peer_address, None)
            print(f"Peer {peer_address} disconnected")

    def stop(self):
        """Stop the chat network"""
        self.running = False
        for peer_socket in self.peers.values():
            peer_socket.close()
        self.peers.clear()
        if self.server_socket:
            self.server_socket.close()
