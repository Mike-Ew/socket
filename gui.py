import tkinter as tk
from tkinter import ttk, scrolledtext, simpledialog, messagebox, filedialog
import time
import os
from datetime import datetime
from chat import ChatRoom


class ChatAppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P Chat")
        self.root.geometry("900x600")
        self.root.minsize(800, 500)

        # Color scheme
        self.colors = {
            "primary": "#FF8C00",  # Orange
            "primary_dark": "#E67E00",  # Darker orange
            "background": "#FFFFFF",  # White
            "text": "#333333",  # Dark gray
            "light_gray": "#F5F5F5",  # Light gray for alternating messages
            "sender_bg": "#FFE0B2",  # Light orange for sent messages
            "system_bg": "#E8E8E8",  # Light gray for system messages
        }

        self.username = None
        self.chat_room = None

        self.create_styles()
        self.setup_login_screen()

    def create_styles(self):
        # Create custom styles for ttk widgets
        self.style = ttk.Style()
        self.style.configure(
            "Orange.TButton",
            background=self.colors["primary"],
            foreground="#222222",
            font=("Arial", 10, "bold"),
        )

        self.style.map(
            "Orange.TButton", background=[("active", self.colors["primary_dark"])]
        )

        self.style.configure("TFrame", background=self.colors["background"])

        self.style.configure(
            "User.TLabel", background=self.colors["light_gray"], font=("Arial", 10)
        )

        self.style.configure(
            "Header.TLabel",
            background=self.colors["primary"],
            foreground="white",
            font=("Arial", 12, "bold"),
            padding=10,
        )

    def setup_login_screen(self):
        """Setup the login screen"""
        self.login_frame = ttk.Frame(self.root)
        self.login_frame.pack(expand=True, fill="both")

        # Center frame for login
        center_frame = ttk.Frame(self.login_frame)
        center_frame.place(relx=0.5, rely=0.5, anchor="center")

        # App title
        app_title = ttk.Label(
            center_frame,
            text="P2P CHAT",
            font=("Arial", 24, "bold"),
            foreground=self.colors["primary"],
        )
        app_title.pack(pady=20)

        # Username field
        username_frame = ttk.Frame(center_frame)
        username_frame.pack(fill="x", pady=5)

        username_label = ttk.Label(username_frame, text="Username:", font=("Arial", 12))
        username_label.pack(side="left", padx=5)

        self.username_entry = ttk.Entry(username_frame, width=30, font=("Arial", 12))
        self.username_entry.pack(side="right", padx=5)

        # Host field
        host_frame = ttk.Frame(center_frame)
        host_frame.pack(fill="x", pady=5)

        host_label = ttk.Label(host_frame, text="Host:", font=("Arial", 12))
        host_label.pack(side="left", padx=5)

        self.host_entry = ttk.Entry(host_frame, width=30, font=("Arial", 12))
        self.host_entry.insert(0, "localhost")
        self.host_entry.pack(side="right", padx=5)

        # Port field
        port_frame = ttk.Frame(center_frame)
        port_frame.pack(fill="x", pady=5)

        port_label = ttk.Label(port_frame, text="Port:", font=("Arial", 12))
        port_label.pack(side="left", padx=5)

        self.port_entry = ttk.Entry(port_frame, width=30, font=("Arial", 12))
        self.port_entry.insert(0, "5000")
        self.port_entry.pack(side="right", padx=5)

        # Login button
        login_button = ttk.Button(
            center_frame, text="Start Chat", style="Orange.TButton", command=self.login
        )
        login_button.pack(pady=20, padx=20, fill="x")

    def login(self):
        """Handle login and start chat"""
        username = self.username_entry.get().strip()
        host = self.host_entry.get().strip()
        port = self.port_entry.get().strip()

        if not username:
            messagebox.showerror("Error", "Username cannot be empty")
            return

        try:
            port = int(port)
        except ValueError:
            messagebox.showerror("Error", "Port must be a number")
            return

        self.username = username
        self.chat_room = ChatRoom(username, host, port)
        self.chat_room.register_message_callback(self.handle_message)
        self.chat_room.start()

        self.login_frame.destroy()
        self.setup_chat_screen()

    def setup_chat_screen(self):
        """Setup the main chat interface"""
        # Main container
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        # Create a PanedWindow
        self.paned = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        self.paned.pack(fill="both", expand=True)

        # Left panel for users
        self.users_frame = ttk.Frame(self.paned, width=200)
        self.paned.add(self.users_frame, weight=1)

        # Users header
        users_header = ttk.Label(
            self.users_frame, text="Online Users", style="Header.TLabel"
        )
        users_header.pack(fill="x")

        # Users list
        self.users_list = tk.Listbox(
            self.users_frame,
            bg=self.colors["background"],
            fg=self.colors["text"],
            font=("Arial", 11),
            highlightthickness=0,
            bd=0,
        )
        self.users_list.pack(fill="both", expand=True, padx=5, pady=5)

        # Add yourself to users list
        self.users_list.insert(tk.END, f"{self.username} (You)")

        # Add manual refresh button for users list
        refresh_btn = ttk.Button(
            self.users_frame,
            text="Refresh",
            style="Orange.TButton",
            command=self.refresh_users_list,
        )
        refresh_btn.pack(fill="x", padx=5, pady=5)

        # Right panel for chat
        self.chat_frame = ttk.Frame(self.paned)
        self.paned.add(self.chat_frame, weight=3)

        # Chat header with connect section
        self.chat_header = ttk.Frame(self.chat_frame)
        self.chat_header.pack(fill="x")

        # Chat title
        chat_title = ttk.Label(self.chat_header, text="P2P Chat", style="Header.TLabel")
        chat_title.pack(side="left", fill="x", expand=True)

        # Connect section
        connect_frame = ttk.Frame(self.chat_header, padding=5)
        connect_frame.pack(side="right")

        ttk.Label(connect_frame, text="Connect to:").pack(side="left")
        self.connect_host = ttk.Entry(connect_frame, width=15)
        self.connect_host.pack(side="left", padx=5)

        ttk.Label(connect_frame, text="Port:").pack(side="left")
        self.connect_port = ttk.Entry(connect_frame, width=6)
        self.connect_port.pack(side="left", padx=5)

        connect_btn = ttk.Button(
            connect_frame,
            text="Connect",
            style="Orange.TButton",
            command=self.connect_to_peer,
        )
        connect_btn.pack(side="left", padx=5)

        # Chat messages area
        self.chat_display = scrolledtext.ScrolledText(
            self.chat_frame,
            wrap=tk.WORD,
            bg=self.colors["background"],
            font=("Arial", 11),
            state="disabled",
        )
        self.chat_display.pack(fill="both", expand=True, padx=10, pady=10)

        # Configure text tags for different message types
        self.chat_display.tag_configure(
            "user_message", background=self.colors["light_gray"]
        )
        self.chat_display.tag_configure(
            "self_message", background=self.colors["sender_bg"]
        )
        self.chat_display.tag_configure(
            "system_message", background=self.colors["system_bg"]
        )
        self.chat_display.tag_configure(
            "timestamp", foreground="gray", font=("Arial", 9)
        )
        self.chat_display.tag_configure(
            "sender", foreground=self.colors["primary"], font=("Arial", 11, "bold")
        )

        # Add a frame for active file transfers below the chat display
        self.transfers_frame = ttk.LabelFrame(self.chat_frame, text="Active Transfers")
        self.transfers_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Dictionary to track transfer progress bars
        self.transfer_progress = {}

        # Hide transfers frame initially
        self.transfers_frame.pack_forget()

        # Message input area
        input_frame = ttk.Frame(self.chat_frame)
        input_frame.pack(fill="x", padx=10, pady=10)

        self.message_input = ttk.Entry(input_frame, font=("Arial", 11))
        self.message_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.message_input.bind("<Return>", lambda e: self.send_message())

        # Add file send button
        file_btn = ttk.Button(
            input_frame,
            text="Send File",
            style="Orange.TButton",
            command=self.send_file,
        )
        file_btn.pack(side="right", padx=5)

        send_btn = ttk.Button(
            input_frame, text="Send", style="Orange.TButton", command=self.send_message
        )
        send_btn.pack(side="right")

        # Focus the input field
        self.message_input.focus()

        # Setup protocol for closing the window properly
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def connect_to_peer(self):
        """Connect to another peer"""
        host = self.connect_host.get().strip()
        port_str = self.connect_port.get().strip()

        if not host or not port_str:
            messagebox.showerror("Error", "Host and port are required")
            return

        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Error", "Port must be a number")
            return

        if self.chat_room.connect_to_peer(host, port):
            self.add_system_message(f"Connected to {host}:{port}")
        else:
            messagebox.showerror("Error", f"Failed to connect to {host}:{port}")

    def send_message(self):
        """Send a message to all peers"""
        message = self.message_input.get().strip()
        if not message:
            return

        if self.chat_room.send_message(message):
            # Message successfully sent to peers
            self.display_message(
                {
                    "type": "chat",
                    "sender": self.username,
                    "content": message,
                    "timestamp": time.time(),
                    "is_self": True,
                }
            )
            self.message_input.delete(0, tk.END)
        else:
            # No peers to send to
            self.add_system_message("No peers connected. Message not sent.")

    def send_file(self):
        """Open file dialog and send selected file"""
        file_path = filedialog.askopenfilename(
            title="Select File to Send", filetypes=[("All Files", "*.*")]
        )

        if file_path:
            # Show the transfers frame when sending a file
            self.transfers_frame.pack(fill="x", padx=10, pady=(0, 10))

            if self.chat_room.send_file(file_path):
                self.add_system_message(f"Sending file: {os.path.basename(file_path)}")

                # Add a progress bar for this transfer
                transfer_id = (
                    f"sending_{int(time.time())}_{os.path.basename(file_path)}"
                )
                self._add_transfer_progress(
                    transfer_id, f"Sending: {os.path.basename(file_path)}"
                )

                # Start progress monitoring
                self._update_transfer_progress()
            else:
                messagebox.showerror(
                    "Error", "Failed to send file. No peers connected."
                )

    def _add_transfer_progress(self, transfer_id, label_text):
        """Add a progress bar for a file transfer"""
        # Create a frame for this transfer
        transfer_frame = ttk.Frame(self.transfers_frame)
        transfer_frame.pack(fill="x", padx=5, pady=2)

        # Label for the transfer
        transfer_label = ttk.Label(transfer_frame, text=label_text)
        transfer_label.pack(side="left", padx=5)

        # Progress bar
        progress = ttk.Progressbar(transfer_frame, length=200, mode="determinate")
        progress.pack(side="left", fill="x", expand=True, padx=5)

        # Status label
        status_label = ttk.Label(transfer_frame, text="0%")
        status_label.pack(side="left", padx=5)

        # Store references
        self.transfer_progress[transfer_id] = {
            "frame": transfer_frame,
            "progress": progress,
            "status": status_label,
            "start_time": time.time(),
        }

    def _update_transfer_progress(self):
        """Update all transfer progress bars"""
        if not hasattr(self.chat_room, "file_manager"):
            return

        for transfer_id in list(self.transfer_progress.keys()):
            # Get current status from file manager
            status = None

            # For real transfer IDs (not our temporary ones for UI)
            if not transfer_id.startswith("sending_"):
                status = self.chat_room.file_manager.get_transfer_status(transfer_id)

            if status:
                # Update progress bar
                progress_widget = self.transfer_progress[transfer_id]["progress"]
                status_label = self.transfer_progress[transfer_id]["status"]

                progress_widget["value"] = status["progress"]
                status_label["text"] = f"{int(status['progress'])}%"

                # Remove completed transfers after a delay
                if (
                    status["status"] == "completed"
                    and time.time() - self.transfer_progress[transfer_id]["start_time"]
                    > 5
                ):
                    self.transfer_progress[transfer_id]["frame"].destroy()
                    del self.transfer_progress[transfer_id]
            else:
                # For UI-only transfer IDs or if transfer is no longer tracked
                elapsed = (
                    time.time() - self.transfer_progress[transfer_id]["start_time"]
                )
                if elapsed > 30:  # Remove after 30 seconds if no updates
                    self.transfer_progress[transfer_id]["frame"].destroy()
                    del self.transfer_progress[transfer_id]

        # Hide transfers frame if empty
        if not self.transfer_progress:
            self.transfers_frame.pack_forget()

        # Schedule next update
        self.root.after(1000, self._update_transfer_progress)

    def handle_message(self, message):
        """Callback for handling incoming messages from the chat room"""
        if message.get("type") == "user_update":
            self.update_users_list(message.get("users", []))
            return

        # Show transfers frame when receiving a file
        if message.get("type") == "system" and "Receiving file" in message.get(
            "content", ""
        ):
            self.transfers_frame.pack(fill="x", padx=10, pady=(0, 10))

            # Extract transfer ID if possible
            content = message.get("content", "")
            if "transfer_id" in message:
                transfer_id = message["transfer_id"]

        self.display_message(message)

    def display_message(self, message):
        """Display a message in the chat area"""
        self.chat_display.config(state="normal")

        # Add a newline if not the first message
        if self.chat_display.get("1.0", "1.end"):
            self.chat_display.insert(tk.END, "\n")

        # Format timestamp
        timestamp = message.get("timestamp", time.time())
        formatted_time = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")

        msg_type = message.get("type")

        # Position for the start of this message
        message_start = self.chat_display.index(tk.END)

        # Add timestamp
        self.chat_display.insert(tk.END, f"[{formatted_time}] ", "timestamp")

        if msg_type == "chat":
            # Add sender's name
            self.chat_display.insert(tk.END, f"{message['sender']}: ", "sender")
            # Add message content
            self.chat_display.insert(tk.END, message["content"])

            # Apply tag to entire message based on sender
            message_end = self.chat_display.index(tk.END)
            if message.get("is_self", False):
                self.chat_display.tag_add("self_message", message_start, message_end)
            else:
                self.chat_display.tag_add("user_message", message_start, message_end)

        elif msg_type == "system":
            # System message
            self.chat_display.insert(tk.END, message["content"])
            message_end = self.chat_display.index(tk.END)
            self.chat_display.tag_add("system_message", message_start, message_end)

        self.chat_display.config(state="disabled")
        self.chat_display.see(tk.END)

    def add_system_message(self, content):
        """Add a system message to the chat"""
        system_msg = {"type": "system", "content": content, "timestamp": time.time()}
        self.display_message(system_msg)

    def update_users_list(self, users):
        """Update the list of online users"""
        self.users_list.delete(0, tk.END)

        # Always add yourself first
        self.users_list.insert(tk.END, f"{self.username} (You)")

        # Add other users
        for user in users:
            if user != self.username:
                self.users_list.insert(tk.END, user)

        # Update window title with user count
        user_count = len(users) if self.username not in users else len(users) + 1
        self.root.title(f"P2P Chat - {self.username} - {user_count} users online")

    def refresh_users_list(self):
        """Manually trigger a refresh of the users list"""
        if self.chat_room:
            self.add_system_message("Refreshing peer list...")
            # This will trigger presence updates and refresh the list
            self.chat_room._refresh_peer_list()

    def on_close(self):
        """Handle window closing"""
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            if self.chat_room:
                self.chat_room.stop()
            self.root.destroy()


def start_gui():
    root = tk.Tk()
    app = ChatAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    start_gui()
