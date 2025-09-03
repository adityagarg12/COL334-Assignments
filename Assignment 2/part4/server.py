import socket
import select
import sys
from typing import List


class Config:
    def __init__(self):
        self.server_ip = ""
        self.server_port = 0
        self.filename = ""

class WordServer:
    def __init__(self, config_file: str = "config.json"):
        """Initialize the server with configuration."""
        self.config = self.load_config(config_file)
        self.words = []
        self.load_words_from_file()
        self.server_socket = None
        self.client_sockets = []  # List to track connected clients in a fixed order
        self.max_clients = 32
        
        # NEW: Index to track the next client to serve for round-robin
        self.next_client_index = 0

    # The load_config, load_words_from_file, process_request,
    # handle_new_connection, handle_client_message, remove_client,
    # and cleanup methods are IDENTICAL to the previous version.
    # The only significant change is in the main loop of start_server.

    def load_config(self, config_file: str) -> Config:
        """Load configuration from JSON file using custom parser."""
        config = Config()
        try:
            with open(config_file, 'r') as f:
                lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                if '"server_ip"' in line:
                    colon_pos = line.find(':')
                    if colon_pos != -1:
                        quote_start = line.find('"', colon_pos)
                        if quote_start != -1:
                            quote_end = line.find('"', quote_start + 1)
                            if quote_end != -1:
                                config.server_ip = line[quote_start + 1:quote_end]
                elif '"server_port"' in line:
                    colon_pos = line.find(':')
                    if colon_pos != -1:
                        num_str = line[colon_pos + 1:]
                        clean_num = "".join(c for c in num_str if c.isdigit())
                        if clean_num:
                            config.server_port = int(clean_num)
                elif '"filename"' in line:
                    colon_pos = line.find(':')
                    if colon_pos != -1:
                        quote_start = line.find('"', colon_pos)
                        if quote_start != -1:
                            quote_end = line.find('"', quote_start + 1)
                            if quote_end != -1:
                                config.filename = line[quote_start + 1:quote_end]
            print(f"Server Configuration:\nIP: {config.server_ip}\nPort: {config.server_port}\nFilename: {config.filename}\n")
            return config
        except FileNotFoundError:
            print(f"Failed to open config file: {config_file}")
            sys.exit(1)

    def load_words_from_file(self):
        """Load words from the specified file."""
        try:
            with open(self.config.filename, 'r') as f:
                content = f.read().strip()
                self.words = content.split(',')
            print(f"Loaded {len(self.words)} words from {self.config.filename}")
        except FileNotFoundError:
            print(f"Failed to open file: {self.config.filename}")
            sys.exit(1)

    def process_request(self, request: str) -> str:
        """Process a client request and return the response."""
        print(f"Received request: {request.strip()}")
        try:
            parts = request.strip().split(',')
            if len(parts) != 2:
                return "Invalid request format\n"
            p = int(parts[0])
            k = int(parts[1])
            print(f"Request: offset={p}, count={k}")
            if p >= len(self.words):
                response = "EOF\n"
            else:
                words_to_send = min(k, len(self.words) - p)
                reached_eof = (p + k >= len(self.words))
                response_words = self.words[p : p + words_to_send]
                response = ','.join(response_words)
                if reached_eof:
                    response += ",EOF"
                response += "\n"
            print(f"Sending response: {response.strip()}")
            return response
        except (ValueError, IndexError):
            return "Invalid request format\n"

    def handle_new_connection(self):
        """Handle new client connection."""
        try:
            client_socket, client_address = self.server_socket.accept()
            client_socket.setblocking(False)
            if len(self.client_sockets) >= self.max_clients:
                print(f"Max clients ({self.max_clients}) reached. Rejecting new client from {client_address}")
                client_socket.close()
                return
            self.client_sockets.append(client_socket)
            print(f"Client connected from {client_address} (Total clients: {len(self.client_sockets)})")
        except socket.error as e:
            print(f"Error accepting new connection: {e}")

    def handle_client_message(self, client_socket):
        """Handle message from existing client."""
        try:
            data = client_socket.recv(1024)
            if not data:
                print("Client disconnected")
                self.remove_client(client_socket)
                return
            request = data.decode('utf-8')
            response = self.process_request(request)
            client_socket.send(response.encode('utf-8'))
            print("*" * 50)
        except socket.error as e:
            print(f"Error handling client message: {e}")
            self.remove_client(client_socket)

    def remove_client(self, client_socket):
        """Remove client from the list and close socket."""
        if client_socket in self.client_sockets:
            # Get index before removing to adjust the round-robin pointer
            idx = self.client_sockets.index(client_socket)
            self.client_sockets.remove(client_socket)
            
            # If the removed client was before or at the current pointer,
            # the pointer needs to be shifted back to maintain order.
            if idx < self.next_client_index:
                self.next_client_index -= 1
            # Ensure the pointer is valid after any removal
            if self.client_sockets and self.next_client_index >= len(self.client_sockets):
                self.next_client_index = 0

            print(f"Removed client (Remaining clients: {len(self.client_sockets)})")
        try:
            client_socket.close()
        except socket.error:
            pass
            
    def start_server(self):
        """Start the server using select() for I/O multiplexing."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setblocking(False)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        server_ip = self.config.server_ip if self.config.server_ip != "INADDR_ANY" else ''
        self.server_socket.bind((server_ip, self.config.server_port))
        self.server_socket.listen(self.max_clients)
        print(f"Server listening on {self.config.server_ip}:{self.config.server_port}")

        while True:
            try:
                read_sockets = [self.server_socket] + self.client_sockets
                
                ready_to_read, _, _ = select.select(read_sockets, [], [], 1.0)
                
                # 1. Always check for new connections first
                if self.server_socket in ready_to_read:
                    self.handle_new_connection()
                
                # --- START OF ROUND-ROBIN LOGIC ---
                # 2. Serve ONE client based on the round-robin schedule.
                if self.client_sockets: # Only proceed if there are clients
                    # Iterate through all clients once, starting from the next one in line
                    for _ in range(len(self.client_sockets)):
                        client_to_check = self.client_sockets[self.next_client_index]
                        
                        # Check if it's this client's turn AND if they have sent data
                        if client_to_check in ready_to_read:
                            self.handle_client_message(client_to_check)
                            
                            # A client might disconnect in handle_client_message,
                            # so we check if the list is still valid.
                            if not self.client_sockets:
                                self.next_client_index = 0
                                break
                                
                            # Move pointer to the next client for the next round
                            self.next_client_index = (self.next_client_index + 1) % len(self.client_sockets)
                            
                            # IMPORTANT: Break after serving one client
                            break 
                        else:
                            # If this client has no data, move the pointer to check the next one
                            self.next_client_index = (self.next_client_index + 1) % len(self.client_sockets)
                # --- END OF ROUND-ROBIN LOGIC ---

            except KeyboardInterrupt:
                print("\nServer shutting down...")
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
        
        self.cleanup()

    def cleanup(self):
        """Clean up server resources."""
        print("Cleaning up server resources...")
        for client_socket in self.client_sockets[:]:
            self.remove_client(client_socket)
        if self.server_socket:
            self.server_socket.close()
        print("Server shut down")

def main():
    """Main function to start the server."""
    # Assuming config.json is in the same directory
    server = WordServer(config_file="config.json")
    server.start_server()

if __name__ == "__main__":
    main()
