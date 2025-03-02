from enum import Enum
import time
import json
from typing import Dict, Set, Tuple
import logging
from network import ChatNetwork
from file_transfer import FileTransferManager


class MessageType(Enum):
    CHAT = "chat"
    PRESENCE = "presence"
    SYSTEM = "system"


class UserStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class ChatUser:
    def __init__(self, username: str, address: Tuple[str, int]):
        self.username = username
        self.address = address
        self.status = UserStatus.OFFLINE
        self.last_seen = 0


class ChatRoom:
    def __init__(self, username: str, host: str = "localhost", port: int = 5000):
        self.username = username
        logging.basicConfig(
            filename=f"chat_debug_{username}.log",
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s",
        )
        self.logger = logging.getLogger(__name__)
        self.network = ChatNetwork(host, port)
        self.users: Dict[Tuple[str, int], ChatUser] = {}
        self.message_history: list = []
        self.MAX_HISTORY = 100
        self.message_callbacks = []
        self.file_manager = FileTransferManager(self)

    def register_message_callback(self, callback):
        """Register a callback function to be called when a message is received"""
        self.message_callbacks.append(callback)

    def start(self):
        """Start the chat room"""
        self.network.start(message_callback=self._handle_message)
        self._set_status(UserStatus.ONLINE)
        # Initiate periodic peer list refresh
        self._start_peer_refresh_timer()

    def _start_peer_refresh_timer(self):
        """Start a timer to periodically refresh the peer list"""
        import threading

        if hasattr(self, "_peer_refresh_timer") and self._peer_refresh_timer:
            self._peer_refresh_timer.cancel()

        self._peer_refresh_timer = threading.Timer(30.0, self._refresh_peer_list)
        self._peer_refresh_timer.daemon = True
        self._peer_refresh_timer.start()

    def _refresh_peer_list(self):
        """Refresh the peer list and notify callbacks"""
        # Send presence update to ensure all peers are aware of each other
        self._send_presence_update()

        # Notify callbacks about current user list
        system_message = {
            "type": "user_update",
            "users": self.get_online_users(),
            "timestamp": time.time(),
        }
        for callback in self.message_callbacks:
            callback(system_message)

        # Restart timer
        self._start_peer_refresh_timer()

    def connect_to_peer(self, peer_host: str, peer_port: int) -> bool:
        """Connect to a peer and exchange presence info"""
        # Don't connect to self
        if peer_host in ("localhost", "127.0.0.1") and peer_port == self.network.port:
            return False

        success = self.network.connect_to_peer(peer_host, peer_port)
        if success:
            # Send immediate presence update after connection
            presence_message = {
                "type": MessageType.PRESENCE.value,
                "username": self.username,
                "status": UserStatus.ONLINE.value,
                "timestamp": time.time(),
            }
            peer_address = (peer_host, peer_port)
            self.network.send_to_peer(peer_address, presence_message)

            # Trigger peer list refresh
            self._refresh_peer_list()
        return success

    def send_message(self, message: str):
        """Send a chat message to all peers"""
        chat_message = {
            "type": MessageType.CHAT.value,
            "sender": self.username,
            "content": message,
            "timestamp": time.time(),
        }
        self._add_to_history(chat_message)
        success = self._broadcast_message(chat_message)
        return success

    def _handle_message(self, sender_address: Tuple[str, int], message: dict) -> None:
        """Handle incoming messages with type filtering"""
        msg_type = message.get("type")

        if msg_type == "heartbeat":
            # Silently handle heartbeats
            return

        elif msg_type == MessageType.CHAT.value:
            # Handle chat messages
            self._handle_chat_message(sender_address, message)

        elif msg_type == MessageType.PRESENCE.value:
            # Update user presence
            self._handle_presence_update(sender_address, message)

        elif msg_type == MessageType.SYSTEM.value:
            # Handle system messages
            self._handle_system_message(message)

        # Handle file transfer related messages - extended to handle more message types
        elif msg_type in [
            "file_metadata",
            "file_chunk",
            "file_transfer_complete",
            "file_chunk_ack",
            "file_chunk_request",
        ]:
            notification = self.file_manager.handle_file_message(message)
            if notification:
                for callback in self.message_callbacks:
                    callback(notification)

    def _handle_chat_message(self, sender_address: Tuple[str, int], message: dict):
        """Process chat messages"""
        self._add_to_history(message)
        # Notify all registered callbacks about the new message
        for callback in self.message_callbacks:
            callback(message)

    def _handle_system_message(self, message: dict):
        """Handle system messages"""
        self._add_to_history(message)
        for callback in self.message_callbacks:
            callback(message)

    def _handle_presence_update(self, sender_address: Tuple[str, int], message: dict):
        """Handle user presence updates"""
        username = message["username"]
        status = UserStatus(message["status"])

        if sender_address not in self.users:
            self.users[sender_address] = ChatUser(username, sender_address)
            # New user connected - notify
            system_message = {
                "type": MessageType.SYSTEM.value,
                "content": f"{username} connected",
                "timestamp": time.time(),
            }
            for callback in self.message_callbacks:
                callback(system_message)

        self.users[sender_address].status = status
        self.users[sender_address].last_seen = time.time()

        # Always notify callbacks about user list changes
        user_update = {
            "type": "user_update",
            "users": self.get_online_users(),
            "timestamp": time.time(),
        }
        for callback in self.message_callbacks:
            callback(user_update)

    def _send_presence_update(self):
        """Send presence update to all peers"""
        presence_message = {
            "type": MessageType.PRESENCE.value,
            "username": self.username,
            "status": UserStatus.ONLINE.value,
            "timestamp": time.time(),
        }
        self._broadcast_message(presence_message)

    def _broadcast_message(self, message: dict) -> bool:
        """Send message to all connected peers"""
        if not self.users:
            return False

        success = False
        for peer_address in list(self.users.keys()):
            if self.network.send_to_peer(peer_address, message):
                success = True
        return success

    def _add_to_history(self, message: dict):
        """Add message to chat history"""
        self.message_history.append(message)
        if len(self.message_history) > self.MAX_HISTORY:
            self.message_history.pop(0)

    def _set_status(self, status: UserStatus):
        """Update user status and notify peers"""
        presence_message = {
            "type": MessageType.PRESENCE.value,
            "username": self.username,
            "status": status.value,
            "timestamp": time.time(),
        }
        self._broadcast_message(presence_message)

    def stop(self):
        """Stop the chat room"""
        if hasattr(self, "_peer_refresh_timer") and self._peer_refresh_timer:
            self._peer_refresh_timer.cancel()
        self._set_status(UserStatus.OFFLINE)
        if hasattr(self.file_manager, "stop"):
            self.file_manager.stop()
        self.network.stop()

    def get_online_users(self) -> list:
        """Get list of online users"""
        return [
            user.username
            for user in self.users.values()
            if user.status == UserStatus.ONLINE
        ]

    def get_message_history(self):
        """Get message history"""
        return self.message_history

    def send_file(self, file_path: str) -> bool:
        """Send a file to all peers"""
        return self.file_manager.send_file(file_path)
