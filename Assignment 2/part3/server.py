import socket
import threading
import json
import time
import os
import sys

class MultithreadedWordServer:
    def __init__(self, config_file: str = "config.json"):
        self.config = self.load_config(config_file)
        self.words = []
        self.load_words_from_file()
        self.server_socket = None
        self.client_count = 0
        self.client_lock = threading.Lock()  # For thread-safe client counting

    def load_config(self, config_file: str) -> dict:
        config = {
            "server_ip": "10.0.0.100",
            "server_port": 5000
        }
        try:
            with open(config_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("//"):
                        continue
                    if '"server_ip"' in line:
                        colon = line.find(":")
                        quote1 = line.find('"', colon)
                        quote2 = line.find('"', quote1 + 1)
                        if quote1 != -1 and quote2 != -1:
                            config["server_ip"] = line[quote1 + 1:quote2]
                    elif '"server_port"' in line:
                        colon = line.find(":")
                        num = ''.join(c for c in line[colon+1:] if c.isdigit())
                        if num:
                            config["server_port"] = int(num)
                    elif '"port"' in line:
                        colon = line.find(":")
                        num = ''.join(c for c in line[colon+1:] if c.isdigit())
                        if num:
                            config["server_port"] = int(num)
                    elif '"k"' in line:
                        colon = line.find(":")
                        num = ''.join(c for c in line[colon+1:] if c.isdigit())
                        if num:
                            config["k"] = int(num)
                    elif '"p"' in line:
                        colon = line.find(":")
                        num = ''.join(c for c in line[colon+1:] if c.isdigit())
                        if num:
                            config["p"] = int(num)
                    elif '"filename"' in line:
                        colon = line.find(":")
                        quote1 = line.find('"', colon)
                        quote2 = line.find('"', quote1 + 1)
                        if quote1 != -1 and quote2 != -1:
                            config["filename"] = line[quote1 + 1:quote2]
            return config
        except:
            return config

    def load_words_from_file(self):
        filename = self.config.get("filename", "words.txt")
        with open(filename, 'r') as f:
            content = f.read().strip()
            self.words = [word.strip() for word in content.split(',') if word.strip()]
        print(f"server loaded {len(self.words)} words from {filename}")

    def process_request(self, request: str) -> str:
       
        try:
            parts = request.strip().split(',')
            if len(parts) != 2:
                return "Invalid request\n"

            p = int(parts[0])  # offset
            k = int(parts[1])  # number of words

            if p >= len(self.words):
                return "EOF\n"

            words_to_send = min(k, len(self.words) - p)
            reached_eof = (p + k >= len(self.words))

            if words_to_send > 0:
                response_words = self.words[p:p + words_to_send]
                response = ','.join(response_words)
                if reached_eof:
                    response += ",EOF"
            else:
                response = "EOF"

            return response + "\n"
        except:
            return "Invalid request\n"

    def handle_client_thread(self, client_socket, client_address, client_id):
       
        thread_name = threading.current_thread().name
      

        try:
            buffer = ""
            requests_processed = 0
            start_time = time.time()

            while True:
                # Read data from client
                try:
                    data = client_socket.recv(4096).decode('utf-8')
                    if not data:
                        break  # Client disconnected
                    buffer += data
                except:
                    break

                # Process ALL complete requests in buffer
                while '\n' in buffer:
                    request, buffer = buffer.split('\n', 1)
                    if request.strip():
                        requests_processed += 1

                        # Process this request
                        response = self.process_request(request)
                        client_socket.send(response.encode('utf-8'))

                        # Log every 50 requests to show progress
                        if requests_processed % 50 == 0:
                            elapsed = time.time() - start_time
                            print(f"[{thread_name}] ⚡ Client {client_id}: {requests_processed} requests in {elapsed:.2f}s")

                        # Check if we sent EOF
                        if "EOF" in response:
                            print(f"[{thread_name}] 🏁 Client {client_id}: EOF sent after {requests_processed} requests")
                            break

                if "EOF" in buffer or "EOF" in (response if 'response' in locals() else ""):
                    break

            end_time = time.time()
            total_time = end_time - start_time
            print(f"[{thread_name}] ✅ Client {client_id} completed: {requests_processed} requests in {total_time:.3f}s")

        except Exception as e:
            print(f"[{thread_name}]Error handling client {client_id}: {e}")
        finally:
            client_socket.close()
            with self.client_lock:
                self.client_count -= 1
            print(f"[{thread_name}]Client {client_id} disconnected (Active: {self.client_count})")

    def start_server(self):
       
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        server_ip = self.config.get('server_ip', '10.0.0.100')
        server_port = self.config.get('server_port', 5000)

        self.server_socket.bind((server_ip, server_port))
        self.server_socket.listen(50)

       
        try:
            client_counter = 0
            while True:
                # Accept connection (FCFS order)
                client_socket, address = self.server_socket.accept()

                with self.client_lock:
                    self.client_count += 1
                    client_counter += 1
                    client_id = f"C{client_counter}"

                print(f"\nNew client {client_id} from {address} (Active: {self.client_count})")

                # Create dedicated thread for this client
                # Thread name indicates FCFS order
                thread_name = f"FCFS-Client-{client_counter}"
                client_thread = threading.Thread(
                    target=self.handle_client_thread,
                    args=(client_socket, address, client_id),
                    name=thread_name
                )
                client_thread.daemon = True  # Dies when main thread dies
                client_thread.start()

        except KeyboardInterrupt:
            print("\nServer shutting down...")
        finally:
            if self.server_socket:
                self.server_socket.close()
            print("Server shutdown complete")

if __name__ == "__main__":
    server = MultithreadedWordServer()
    server.start_server()
