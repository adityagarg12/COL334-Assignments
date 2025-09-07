import socket
import json
import time
import threading
import sys
import os
import argparse
import queue

class MultithreadedWordClient:
    def __init__(self, client_id, batch_size=1):
        self.client_id = client_id
        self.batch_size = batch_size
        self.config = self.load_config()
        os.makedirs("logs", exist_ok=True)

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            if 'server_port' not in config and 'port' in config:
                config['server_port'] = config['port']
            return config
        except:
            return {"server_ip": "10.0.0.100", "port": 5000, "server_port": 5000, "k": 5}

    def run_client(self):
        """Run client with different strategies based on batch size"""
        server_ip = self.config.get('server_ip', '10.0.0.100')
        server_port = self.config.get('server_port', 5000)
        k = self.config.get('k', 5)

        

        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((server_ip, server_port))

            start_time = time.time()
            full_word_list = []

            if self.batch_size == 1:
                # Normal client: sequential request-response
                self.run_normal_client(client_socket, k, full_word_list)
            else:
                # Greedy client: fire all requests rapidly then read responses
                self.run_greedy_client(client_socket, k, full_word_list)

            end_time = time.time()
            completion_time = end_time - start_time

            print(f"✅ Client {self.client_id} completed in {completion_time:.6f}s with {len(full_word_list)} words")

            # Log completion time
            with open(f"logs/client_{self.client_id}_time.log", "w") as f:
                f.write(f"{completion_time:.6f}\n")

        except Exception as e:
            print(f"❌ Client {self.client_id} error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                client_socket.close()
            except:
                pass

    def run_normal_client(self, client_socket, k, word_list):
        """Normal client: send one request at a time"""
        print(f"📤 Normal client {self.client_id} using sequential requests")

        offset = 0
        request_count = 0

        while True:
            request_count += 1
            request = f"{offset},{k}\n"

            # Send request
            client_socket.send(request.encode('utf-8'))

            # Read response immediately
            response_data = client_socket.recv(4096).decode('utf-8').strip()

            if self.process_response(response_data, word_list):
                break  # EOF reached

            offset += k

            # Progress logging
            if request_count % 50 == 0:
                print(f"   📊 Normal client {self.client_id}: {request_count} requests, {len(word_list)} words")

        print(f"   ✅ Normal client {self.client_id}: {request_count} requests completed")

    def run_greedy_client(self, client_socket, k, word_list):
        """Greedy client: send ALL requests rapidly, then read all responses"""
        print(f"🔥 GREEDY client {self.client_id} using batch_size={self.batch_size}")

        # Estimate total requests needed (overestimate to ensure we get everything)
        total_words_estimate = 800  # Approximate total words in file
        max_requests = (total_words_estimate // k) + 10  # Add buffer

        print(f"   🎯 Firing up to {max_requests} requests as fast as possible...")

        # Phase 1: FIRE ALL REQUESTS AS FAST AS POSSIBLE
        requests_sent = 0
        start_send_time = time.time()

        for i in range(max_requests):
            offset = i * k
            request = f"{offset},{k}\n"

            try:
                client_socket.send(request.encode('utf-8'))
                requests_sent += 1

                # Batch sending for greedy behavior
                if requests_sent % self.batch_size == 0:
                    time.sleep(0.001)  # Tiny delay between batches

            except:
                break

        send_time = time.time() - start_send_time
        print(f"   ⚡ GREEDY: Sent {requests_sent} requests in {send_time:.3f}s ({requests_sent/send_time:.0f} req/s)")

        # Phase 2: READ ALL RESPONSES
        print(f"   📥 Reading responses...")

        buffer = ""
        responses_received = 0
        start_read_time = time.time()

        while responses_received < requests_sent:
            try:
                data = client_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                buffer += data

                # Process complete responses
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    response = line.strip()

                    if response:
                        responses_received += 1

                        # Progress logging
                        if responses_received % 100 == 0:
                            elapsed = time.time() - start_read_time
                            print(f"      📊 Received {responses_received}/{requests_sent} responses in {elapsed:.2f}s")

                        if self.process_response(response, word_list):
                            # EOF reached
                            print(f"      🏁 EOF reached after {responses_received} responses")
                            return

            except:
                break

        read_time = time.time() - start_read_time
        print(f"   ✅ GREEDY: Read {responses_received} responses in {read_time:.3f}s")

    def process_response(self, response, word_list):
        """Process response and return True if EOF reached"""
        if "EOF" in response:
            if response != "EOF":
                words = response.replace(",EOF", "").split(',')
                valid_words = [w.strip() for w in words if w.strip()]
                word_list.extend(valid_words)
            return True  # EOF reached
        else:
            words = response.split(',')
            valid_words = [w.strip() for w in words if w.strip()]
            word_list.extend(valid_words)
            return False

def main():
    parser = argparse.ArgumentParser(description='Multithreaded word client')
    parser.add_argument('--client-id', required=True, help='Client identifier')
    parser.add_argument('--batch-size', type=int, default=1, help='Batch size (greedy behavior)')

    args = parser.parse_args()

    client = MultithreadedWordClient(args.client_id, args.batch_size)
    client.run_client()

if __name__ == "__main__":
    main()
