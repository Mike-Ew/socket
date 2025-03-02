import os
import base64
import hashlib
import json
import time
import tempfile
import logging
from typing import Dict, Callable, Optional, List, Tuple, Set


class FileTransferManager:
    """Manages file transfers in the P2P chat application"""

    def __init__(self, chat_room, download_dir: str = "downloads"):
        self.chat_room = chat_room
        self.download_dir = download_dir
        self.chunk_size = 4096  # Smaller chunks for better progress updates (4KB)
        self.ongoing_transfers = {}  # Track ongoing file transfers
        self.completed_transfers = {}  # Track completed transfers
        self.sending_transfers = {}  # Track outgoing transfers
        self.chunk_acks = {}  # Track acknowledged chunks
        self.retry_limit = 3  # Number of times to retry sending a chunk
        self.chunk_timeout = 10  # Seconds to wait before considering a chunk lost
        self.transfer_timeout = (
            60  # Seconds to wait before considering a transfer stalled
        )

        # Setup logging
        self.logger = logging.getLogger("FileTransfer")
        self.logger.setLevel(logging.DEBUG)

        # Create downloads directory if it doesn't exist
        os.makedirs(self.download_dir, exist_ok=True)

        # Start the monitor thread for transfers
        self._start_transfer_monitor()

    def _start_transfer_monitor(self):
        """Start a background thread to monitor transfers"""
        import threading

        self.monitor_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_transfers)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def _monitor_transfers(self):
        """Monitor ongoing transfers and handle timeouts"""
        while self.monitor_running:
            current_time = time.time()

            # Check sending transfers for timeouts
            for transfer_id in list(self.sending_transfers.keys()):
                transfer = self.sending_transfers[transfer_id]
                if current_time - transfer["last_activity"] > self.transfer_timeout:
                    # Transfer seems stalled, try to resume
                    self._resume_stalled_transfer(transfer_id)

            # Check receiving transfers for timeouts
            for transfer_id in list(self.ongoing_transfers.keys()):
                transfer = self.ongoing_transfers[transfer_id]
                if (
                    current_time - transfer.get("last_activity", transfer["started_at"])
                    > self.transfer_timeout
                ):
                    # Receiving transfer is stalled, request missing chunks
                    self._request_missing_chunks(transfer_id)

            time.sleep(5)  # Check every 5 seconds

    def _resume_stalled_transfer(self, transfer_id):
        """Attempt to resume a stalled outgoing transfer"""
        if transfer_id not in self.sending_transfers:
            return

        transfer = self.sending_transfers[transfer_id]
        # Update activity timestamp
        transfer["last_activity"] = time.time()

        # Get unacknowledged chunks
        if "acked_chunks" not in transfer:
            transfer["acked_chunks"] = set()

        missing_chunks = [
            i
            for i in range(transfer["total_chunks"])
            if i not in transfer["acked_chunks"]
        ]

        self.logger.debug(
            f"Resuming stalled transfer {transfer_id}, resending {len(missing_chunks)} chunks"
        )

        # Resend chunks
        for chunk_index in missing_chunks[
            :20
        ]:  # Limit to 20 chunks at a time to prevent flooding
            self._send_file_chunk(transfer["file_path"], transfer_id, chunk_index)

    def _request_missing_chunks(self, transfer_id):
        """Request missing chunks for a receiving transfer"""
        if transfer_id not in self.ongoing_transfers:
            return

        transfer = self.ongoing_transfers[transfer_id]
        # Update activity timestamp
        transfer["last_activity"] = time.time()

        # Identify missing chunks
        received_chunks = set(transfer["received_chunks"].keys())
        all_chunks = set(range(transfer["total_chunks"]))
        missing_chunks = list(all_chunks - received_chunks)

        if missing_chunks:
            # Request missing chunks from sender
            self.logger.debug(
                f"Requesting {len(missing_chunks)} missing chunks for transfer {transfer_id}"
            )

            # Create message requesting missing chunks
            request_message = {
                "type": "file_chunk_request",
                "transfer_id": transfer_id,
                "chunks": missing_chunks[:50],  # Limit to 50 chunks per request
                "timestamp": time.time(),
            }

            # Send the request
            self.chat_room._broadcast_message(request_message)

            # Update status for user
            return {
                "type": "system",
                "content": f"Transfer stalled. Requesting {len(missing_chunks)} missing chunks...",
                "timestamp": time.time(),
            }

    def send_file(self, file_path: str) -> bool:
        """Initiate a file transfer to all connected peers"""
        if not os.path.exists(file_path):
            return False

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)

        # Generate a unique transfer ID
        transfer_id = f"{int(time.time())}_{self.chat_room.username}_{file_name}"
        file_hash = self._calculate_file_hash(file_path)

        # Calculate total chunks
        total_chunks = (file_size + self.chunk_size - 1) // self.chunk_size

        # Prepare file metadata
        metadata = {
            "type": "file_metadata",
            "transfer_id": transfer_id,
            "file_name": file_name,
            "file_size": file_size,
            "chunk_size": self.chunk_size,
            "total_chunks": total_chunks,
            "file_hash": file_hash,
            "sender": self.chat_room.username,
            "timestamp": time.time(),
        }

        # Track this outgoing transfer
        self.sending_transfers[transfer_id] = {
            "file_path": file_path,
            "file_size": file_size,
            "total_chunks": total_chunks,
            "started_at": time.time(),
            "last_activity": time.time(),
            "status": "sending",
            "acked_chunks": set(),
            "retry_counts": {},
        }

        # Send file metadata to all peers
        if not self.chat_room._broadcast_message(metadata):
            del self.sending_transfers[transfer_id]
            return False

        # Start sending file chunks
        import threading

        send_thread = threading.Thread(
            target=self._send_file_chunks, args=(file_path, transfer_id)
        )
        send_thread.daemon = True
        send_thread.start()

        return True

    def _send_file_chunks(self, file_path: str, transfer_id: str):
        """Send file in chunks to all peers"""
        if transfer_id not in self.sending_transfers:
            return

        transfer = self.sending_transfers[transfer_id]
        total_chunks = transfer["total_chunks"]

        # Send chunks with throttling to prevent network congestion
        for chunk_index in range(total_chunks):
            self._send_file_chunk(file_path, transfer_id, chunk_index)

            # Throttling - don't send too many chunks at once
            if chunk_index % 10 == 0:
                time.sleep(0.1)

        # After all chunks are sent initially, wait for acknowledgments
        wait_start = time.time()
        while (
            transfer_id in self.sending_transfers
            and len(self.sending_transfers[transfer_id]["acked_chunks"]) < total_chunks
        ):
            time.sleep(0.5)

            # Break after reasonable timeout (30 seconds)
            if time.time() - wait_start > 30:
                break

        # Send transfer complete message
        complete_message = {
            "type": "file_transfer_complete",
            "transfer_id": transfer_id,
            "sender": self.chat_room.username,
            "timestamp": time.time(),
        }
        self.chat_room._broadcast_message(complete_message)

    def _send_file_chunk(self, file_path: str, transfer_id: str, chunk_index: int):
        """Send a single file chunk"""
        if transfer_id not in self.sending_transfers:
            return False

        # Update activity timestamp
        self.sending_transfers[transfer_id]["last_activity"] = time.time()

        try:
            with open(file_path, "rb") as f:
                # Seek to the chunk position
                f.seek(chunk_index * self.chunk_size)
                # Read the chunk
                chunk = f.read(self.chunk_size)

                if chunk:
                    # Encode the binary data to base64 for JSON compatibility
                    encoded_chunk = base64.b64encode(chunk).decode("utf-8")

                    # Create chunk message
                    chunk_message = {
                        "type": "file_chunk",
                        "transfer_id": transfer_id,
                        "chunk_index": chunk_index,
                        "data": encoded_chunk,
                        "sender": self.chat_room.username,
                        "timestamp": time.time(),
                    }

                    # Send chunk to all peers
                    success = self.chat_room._broadcast_message(chunk_message)
                    return success
        except Exception as e:
            self.logger.error(
                f"Error sending chunk {chunk_index} for {transfer_id}: {str(e)}"
            )
            return False

    def handle_file_message(self, message: dict) -> Optional[dict]:
        """Handle incoming file transfer related messages"""
        msg_type = message.get("type")

        if msg_type == "file_metadata":
            return self._handle_file_metadata(message)

        elif msg_type == "file_chunk":
            return self._handle_file_chunk(message)

        elif msg_type == "file_transfer_complete":
            return self._handle_transfer_complete(message)

        elif msg_type == "file_chunk_ack":
            return self._handle_chunk_acknowledgment(message)

        elif msg_type == "file_chunk_request":
            return self._handle_chunk_request(message)

        return None

    def _handle_chunk_request(self, message: dict) -> None:
        """Handle request for missing chunks"""
        transfer_id = message.get("transfer_id")
        requested_chunks = message.get("chunks", [])

        if not transfer_id or transfer_id not in self.sending_transfers:
            return None

        self.logger.debug(
            f"Received request for {len(requested_chunks)} chunks of transfer {transfer_id}"
        )

        # Resend requested chunks
        file_path = self.sending_transfers[transfer_id]["file_path"]
        for chunk_index in requested_chunks:
            self._send_file_chunk(file_path, transfer_id, chunk_index)
            # Small delay between chunks to prevent network congestion
            time.sleep(0.05)

        return None

    def _handle_chunk_acknowledgment(self, message: dict) -> None:
        """Handle chunk acknowledgment from receiver"""
        transfer_id = message.get("transfer_id")
        chunk_index = message.get("chunk_index")

        if transfer_id in self.sending_transfers:
            # Mark chunk as acknowledged
            self.sending_transfers[transfer_id]["acked_chunks"].add(chunk_index)
            self.sending_transfers[transfer_id]["last_activity"] = time.time()

            # Check if we need to send a progress update
            total = self.sending_transfers[transfer_id]["total_chunks"]
            acked = len(self.sending_transfers[transfer_id]["acked_chunks"])
            progress = (acked / total) * 100

            # Send progress update every 5%
            if acked == total or acked % max(1, total // 20) == 0:
                return {
                    "type": "system",
                    "content": f"File upload progress: {int(progress)}% ({acked}/{total} chunks)",
                    "timestamp": time.time(),
                }

        return None

    def _handle_file_metadata(self, metadata: dict) -> dict:
        """Handle incoming file metadata and prepare for receiving file"""
        transfer_id = metadata["transfer_id"]
        file_name = metadata["file_name"]
        sender = metadata["sender"]

        # Create a unique filename to avoid overwriting
        base_name, ext = os.path.splitext(file_name)
        unique_filename = f"{base_name}_{int(time.time())}{ext}"
        save_path = os.path.join(self.download_dir, unique_filename)

        # Create a temporary directory for storing chunks if the file is large
        temp_dir = None
        if metadata["file_size"] > 5 * 1024 * 1024:  # For files larger than 5MB
            temp_dir = tempfile.mkdtemp(prefix=f"filetransfer_{transfer_id}_")

        # Initialize transfer tracking
        self.ongoing_transfers[transfer_id] = {
            "file_path": save_path,
            "file_size": metadata["file_size"],
            "received_chunks": {},
            "total_chunks": metadata["total_chunks"],
            "chunk_size": metadata["chunk_size"],
            "file_hash": metadata["file_hash"],
            "sender": sender,
            "started_at": time.time(),
            "last_activity": time.time(),
            "status": "receiving",
            "temp_dir": temp_dir,
        }

        # Create notification message
        return {
            "type": "system",
            "content": f"Receiving file '{file_name}' ({self._format_size(metadata['file_size'])}) from {sender}...",
            "timestamp": time.time(),
        }

    def _format_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"

    def _handle_file_chunk(self, chunk_msg: dict) -> Optional[dict]:
        """Handle an incoming file chunk"""
        transfer_id = chunk_msg["transfer_id"]
        chunk_index = chunk_msg["chunk_index"]
        data = chunk_msg["data"]

        # Check if we're tracking this transfer
        if transfer_id not in self.ongoing_transfers:
            return None

        transfer = self.ongoing_transfers[transfer_id]
        transfer["last_activity"] = time.time()

        # Send acknowledgment
        ack_message = {
            "type": "file_chunk_ack",
            "transfer_id": transfer_id,
            "chunk_index": chunk_index,
            "timestamp": time.time(),
        }
        self.chat_room._broadcast_message(ack_message)

        # Decode chunk data
        try:
            decoded_data = base64.b64decode(data)

            # Store chunk either in memory or on disk
            if transfer.get("temp_dir"):
                # Store on disk for large files
                chunk_path = os.path.join(transfer["temp_dir"], f"chunk_{chunk_index}")
                with open(chunk_path, "wb") as f:
                    f.write(decoded_data)
                transfer["received_chunks"][chunk_index] = chunk_path
            else:
                # Store in memory for smaller files
                transfer["received_chunks"][chunk_index] = decoded_data

            # Calculate progress
            progress = len(transfer["received_chunks"]) / transfer["total_chunks"] * 100

            # Send more frequent progress updates (every 5%)
            if (
                len(transfer["received_chunks"])
                % max(1, transfer["total_chunks"] // 20)
                == 0
            ):
                return {
                    "type": "system",
                    "content": f"File transfer from {transfer['sender']}: {int(progress)}% complete",
                    "timestamp": time.time(),
                }

        except Exception as e:
            self.logger.error(
                f"Error processing chunk {chunk_index} for {transfer_id}: {str(e)}"
            )
            return {
                "type": "system",
                "content": f"Error processing file chunk: {str(e)}",
                "timestamp": time.time(),
            }

        return None

    def _handle_transfer_complete(self, message: dict) -> dict:
        """Handle file transfer completion"""
        transfer_id = message["transfer_id"]

        if transfer_id not in self.ongoing_transfers:
            return {
                "type": "system",
                "content": f"Received file transfer completion for unknown transfer",
                "timestamp": time.time(),
            }

        transfer = self.ongoing_transfers[transfer_id]
        received_chunks = transfer["received_chunks"]

        # Check if we have all chunks
        if len(received_chunks) != transfer["total_chunks"]:
            missing_count = transfer["total_chunks"] - len(received_chunks)
            # Request missing chunks
            return self._request_missing_chunks(transfer_id) or {
                "type": "system",
                "content": f"File transfer incomplete: Missing {missing_count} chunks. Requesting missing data...",
                "timestamp": time.time(),
            }

        # Assemble and write the file
        try:
            with open(transfer["file_path"], "wb") as out_file:
                for i in range(transfer["total_chunks"]):
                    if i in received_chunks:
                        chunk_data = received_chunks[i]
                        if isinstance(chunk_data, str) and os.path.exists(chunk_data):
                            # Read from temp file
                            with open(chunk_data, "rb") as chunk_file:
                                out_file.write(chunk_file.read())
                        else:
                            # Write from memory
                            out_file.write(chunk_data)

            # Verify file hash
            calculated_hash = self._calculate_file_hash(transfer["file_path"])
            if calculated_hash != transfer["file_hash"]:
                os.remove(transfer["file_path"])
                return {
                    "type": "system",
                    "content": f"File transfer failed: Hash verification failed",
                    "timestamp": time.time(),
                }

            # Cleanup temp files
            self._cleanup_temp_files(transfer)

            # Update transfer status
            transfer["status"] = "completed"
            transfer["completed_at"] = time.time()
            self.completed_transfers[transfer_id] = transfer
            del self.ongoing_transfers[transfer_id]

            return {
                "type": "system",
                "content": f"File received successfully: {os.path.basename(transfer['file_path'])}",
                "timestamp": time.time(),
            }

        except Exception as e:
            self.logger.error(f"Error assembling file {transfer_id}: {str(e)}")
            return {
                "type": "system",
                "content": f"Error saving file: {str(e)}",
                "timestamp": time.time(),
            }

    def _cleanup_temp_files(self, transfer):
        """Clean up temporary chunk files"""
        temp_dir = transfer.get("temp_dir")
        if temp_dir and os.path.exists(temp_dir):
            try:
                import shutil

                shutil.rmtree(temp_dir)
            except Exception as e:
                self.logger.error(f"Error cleaning up temp files: {str(e)}")

    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of a file"""
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def get_transfer_status(self, transfer_id: str) -> Optional[dict]:
        """Get status of an ongoing or completed transfer"""
        if transfer_id in self.ongoing_transfers:
            transfer = self.ongoing_transfers[transfer_id]
            progress = len(transfer["received_chunks"]) / transfer["total_chunks"] * 100
            return {
                "status": transfer["status"],
                "progress": progress,
                "file_name": os.path.basename(transfer["file_path"]),
                "sender": transfer["sender"],
            }
        elif transfer_id in self.sending_transfers:
            transfer = self.sending_transfers[transfer_id]
            if "acked_chunks" in transfer:
                progress = (
                    len(transfer["acked_chunks"]) / transfer["total_chunks"] * 100
                )
            else:
                progress = 0
            return {
                "status": "sending",
                "progress": progress,
                "file_name": os.path.basename(transfer["file_path"]),
            }
        elif transfer_id in self.completed_transfers:
            transfer = self.completed_transfers[transfer_id]
            return {
                "status": transfer["status"],
                "progress": 100,
                "file_name": os.path.basename(transfer["file_path"]),
                "sender": transfer["sender"],
                "completed_at": transfer["completed_at"],
            }
        return None

    def stop(self):
        """Stop the file transfer manager and cleanup"""
        self.monitor_running = False

        # Cleanup temp directories
        for transfer_id, transfer in self.ongoing_transfers.items():
            self._cleanup_temp_files(transfer)
