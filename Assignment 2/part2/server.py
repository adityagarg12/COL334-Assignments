import socket
import select
import sys
from typing import List, Dict

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
        self.client_sockets = []  # List to track connected clients (max 32)
        self.max_clients = 32
        
    def load_config(self, config_file: str) -> Config:
        """Load configuration from JSON file using custom parser."""
        config = Config()
        
        try:
            with open(config_file, 'r') as f:
                lines = f.readlines()
            
            for line in lines:
                # Remove spaces and tabs
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
                        clean_num = ""
                        for c in num_str:
                            if c.isdigit():
                                clean_num += c
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
            
            print(f"Server Configuration:")
            print(f"IP: {config.server_ip}")
            print(f"Port: {config.server_port}")
            print(f"Filename: {config.filename}")
            print()
            return config
            
        except FileNotFoundError:
            print(f"Failed to open config file: {config_file}")
            sys.exit(1)
        except Exception as e:
            print(f"Error parsing config file: {e}")
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
            # Parse request in format "p,k\n"
            parts = request.strip().split(',')
            if len(parts) != 2:
                return "Invalid request format\n"
            
            p = int(parts[0])  # offset
            k = int(parts[1])  # number of words
            
            print(f"Request: offset={p}, count={k}")
            
            # Check if offset is beyond file
            if p >= len(self.words):
                response = "EOF\n"
            else:
                # Get k words starting from offset p
                words_to_send = min(k, len(self.words) - p)
                reached_eof = (p + k >= len(self.words))
                
                response_words = []
                for i in range(words_to_send):
                    response_words.append(self.words[p + i])
                
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
            client_socket.setblocking(False)  # Set client socket to non-blocking
            
            # Check if we can accept more clients
            if len(self.client_sockets) >= self.max_clients:
                print(f"Max clients ({self.max_clients}) reached. Rejecting new client from {client_address}")
                client_socket.close()
                return
            
            # Add to client list
            self.client_sockets.append(client_socket)
            print(f"Client connected from {client_address} (Total clients: {len(self.client_sockets)})")
            
        except socket.error as e:
            print(f"Error accepting new connection: {e}")
    
    def handle_client_message(self, client_socket):
        """Handle message from existing client."""
        try:
            data = client_socket.recv(1024)
            if not data:
                # Client disconnected
                print(f"Client disconnected")
                self.remove_client(client_socket)
                return
            
            request = data.decode('utf-8')
            
            # Process the request and get response
            response = self.process_request(request)
            
            # Send response back to client
            client_socket.send(response.encode('utf-8'))
            
            print("*" * 50)
            
        except socket.error as e:
            print(f"Error handling client message: {e}")
            self.remove_client(client_socket)
        except UnicodeDecodeError:
            print("Invalid message format from client")
            self.remove_client(client_socket)
    
    def remove_client(self, client_socket):
        """Remove client from the list and close socket."""
        if client_socket in self.client_sockets:
            self.client_sockets.remove(client_socket)
            print(f"Removed client (Remaining clients: {len(self.client_sockets)})")
        try:
            client_socket.close()
        except:
            pass
    
    def start_server(self):
        """Start the server using select() for I/O multiplexing."""
        try:
            # Create and configure server socket
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setblocking(False)  # Non-blocking mode
            print(f"Socket created successfully")
            
            # Set SO_REUSEADDR
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            print("setsockopt(SO_REUSEADDR) successful")
            
            # Bind socket
            server_ip = self.config.server_ip
            if server_ip == "INADDR_ANY" or server_ip == "":
                server_ip = ''  # Bind to all interfaces
            
            self.server_socket.bind((server_ip, self.config.server_port))
            print("Socket bind successful")
            
            # Listen for connections
            self.server_socket.listen(self.max_clients)
            print(f"Server listening on {self.config.server_ip}:{self.config.server_port}")
            print("Waiting for client connections...")
            
            # Main event loop using select()
            while True:
                try:
                    # Prepare socket lists for select()
                    read_sockets = [self.server_socket] + self.client_sockets
                    write_sockets = []  # Not needed for this application
                    error_sockets = [self.server_socket] + self.client_sockets
                    
                    # Use select() with timeout
                    ready_to_read, ready_to_write, in_error = select.select(
                        read_sockets, write_sockets, error_sockets, 1.0  # 1 second timeout
                    )
                    
                    if ready_to_read or in_error:
                        print("Data is available now!")
                        
                        # Process events sequentially (FIRST-COME-FIRST-SERVE)
                        
                        # 1. Check for new connections first
                        if self.server_socket in ready_to_read:
                            self.handle_new_connection()
                        
                        # 2. Process existing client messages sequentially
                        for client_socket in ready_to_read:
                            if client_socket != self.server_socket:
                                self.handle_client_message(client_socket)
                        
                        # 3. Handle error conditions
                        for client_socket in in_error:
                            if client_socket != self.server_socket:
                                print(f"Error condition on client socket")
                                self.remove_client(client_socket)
                    else:
                        # Timeout - no activity
                        print("Timeout occurred! No data after 1 second.")
                    
                except KeyboardInterrupt:
                    print("\nServer shutting down...")
                    break
                except Exception as e:
                    print(f"Error in main loop: {e}")
                    
        except Exception as e:
            print(f"Server startup error: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up server resources."""
        print("Cleaning up server resources...")
        
        # Close all client connections
        for client_socket in self.client_sockets[:]:  # Copy list to avoid modification during iteration
            self.remove_client(client_socket)
        
        # Close server socket
        if self.server_socket:
            self.server_socket.close()
        
        print("Server shut down")

def main():
    """Main function to start the server."""
    server = WordServer()
    server.start_server()

if __name__ == "__main__":
    main()
