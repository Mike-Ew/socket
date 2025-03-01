import sys
import threading
from chat import ChatRoom


class ChatCLI:
    def __init__(self):
        self.username = None
        self.chat_room = None
        self.commands = {
            "/help": self.show_help,
            "/connect": self.connect_peer,
            "/quit": self.quit,
            "/users": self.list_users,
            "/sendfile": self.send_file,
            "/creategroup": self.create_group,
            "/joingroup": self.join_group,
            "/sendgroup": self.send_group_message,
            "/history": self.show_history,
            "/login": self.authenticate,
        }

    def start(self):
        print("Welcome to P2P Chat!")
        self.username = input("Enter your username: ").strip()
        port = int(input("Enter port to listen on: ").strip())

        self.chat_room = ChatRoom(self.username, port=port)
        self.chat_room.start()

        print("\nChat started! Type /help for commands")
        self._start_input_loop()

    def _start_input_loop(self):
        while True:
            try:
                message = input().strip()
                if not message:
                    continue

                if message.startswith("/"):
                    self._handle_command(message)
                else:
                    self.chat_room.send_message(message)
            except KeyboardInterrupt:
                self.quit()
                break

    def _handle_command(self, command):
        parts = command.split()
        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []

        if cmd in self.commands:
            self.commands[cmd](*args)
        else:
            print("Unknown command. Type /help for available commands.")

    def show_help(self, *args):
        print("\nAvailable commands:")
        print("/connect <host> <port> - Connect to a peer")
        print("/users - List online users")
        print("/sendfile <filename> - Send a file")
        print("/creategroup <name> - Create a chat group")
        print("/joingroup <name> - Join a chat group")
        print("/sendgroup <name> <message> - Send message to group")
        print("/history - Show chat history")
        print("/help - Show this help message")
        print("/quit - Exit the chat")

    def send_file(self, *args):
        if len(args) != 1:
            print("Usage: /sendfile <filename>")
            return
        filename = args[0]
        if self.chat_room.send_file(filename):
            print(f"File {filename} sent successfully")
        else:
            print("Failed to send file")

    def create_group(self, *args):
        if len(args) != 1:
            print("Usage: /creategroup <name>")
            return
        group_name = args[0]
        if self.chat_room.create_group(group_name):
            print(f"Group {group_name} created")
        else:
            print("Failed to create group")

    def join_group(self, *args):
        if len(args) != 1:
            print("Usage: /joingroup <name>")
            return
        group_name = args[0]
        if self.chat_room.join_group(group_name):
            print(f"Joined group {group_name}")
        else:
            print("Failed to join group")

    def send_group_message(self, *args):
        if len(args) < 2:
            print("Usage: /sendgroup <name> <message>")
            return
        group_name = args[0]
        message = " ".join(args[1:])
        if self.chat_room.send_group_message(group_name, message):
            print(f"Message sent to group {group_name}")
        else:
            print("Failed to send group message")

    def authenticate(self, *args):
        if len(args) != 1:
            print("Usage: /login <password>")
            return
        if self.chat_room.authenticate(args[0]):
            print("Authentication successful")
        else:
            print("Authentication failed")

    def show_history(self, *args):
        history = self.chat_room.get_message_history()
        if not history:
            print("No chat history available")
            return
        print("\nChat History:")
        for msg in history:
            print(f"{msg['timestamp']} - {msg['sender']}: {msg['content']}")

    def connect_peer(self, *args):
        if len(args) != 2:
            print("Usage: /connect <host> <port>")
            return
        host, port = args[0], int(args[1])
        if self.chat_room.connect_to_peer(host, port):
            print(f"Connected to {host}:{port}")
        else:
            print("Connection failed")

    def list_users(self, *args):
        users = self.chat_room.get_online_users()
        print("\nOnline users:")
        for user in users:
            print(f"- {user}")

    def quit(self, *args):
        print("\nDisconnecting...")
        if self.chat_room:
            self.chat_room.stop()
        sys.exit(0)


from gui import start_gui

if __name__ == "__main__":
    start_gui()
