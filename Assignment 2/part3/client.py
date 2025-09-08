import socket
# import json
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
        config = {
            "server_ip": "10.0.0.100",
            "server_port": 5000,
            "k": 5,
            "p": 0,
            "filename": "words.txt"
        }
        try:
            with open('config.json', 'r') as f:
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
        except Exception:
            return config

    def run_client(self):
       
        server_ip = self.config.get('server_ip', '10.0.0.100')
        server_port = self.config.get('server_port', 5000)
        k = self.config.get('k', 5)

        

        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((server_ip, server_port))

            start_time = time.time()
            full_word_list = []

            if self.batch_size == 1:
               
                self.run_normal_client(client_socket, k, full_word_list)
            else:
                
                self.run_greedy_client(client_socket, k, full_word_list)

            end_time = time.time()
            completion_time = end_time - start_time

            print(f"Client {self.client_id} completed in {completion_time:.6f}s with {len(full_word_list)} words")

           
            with open(f"logs/client_{self.client_id}_time.log", "w") as f:
                f.write(f"{completion_time:.6f}\n")

        except Exception as e:
            print(f"Client {self.client_id} error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                client_socket.close()
            except:
                pass

    def run_normal_client(self, client_socket, k, word_list):
       

        offset = 0
        request_count = 0

        while True:
            request_count += 1
            request = f"{offset},{k}\n"
        
            client_socket.send(request.encode('utf-8'))
           
            response_data = client_socket.recv(4096).decode('utf-8').strip()

            if self.process_response(response_data, word_list):
                break 
            offset += k
           

    def run_greedy_client(self, client_socket, k, word_list):
       
        total_words_estimate = 800  
        max_requests = (total_words_estimate // k) + 10  

        requests_sent = 0
        start_send_time = time.time()

        for i in range(max_requests):
            offset = i * k
            request = f"{offset},{k}\n"

            try:
                client_socket.send(request.encode('utf-8'))
                requests_sent += 1

                if requests_sent % self.batch_size == 0:
                    time.sleep(0.001)  

            except:
                break

        send_time = time.time() - start_send_time
       

        buffer = ""
        responses_received = 0
        start_read_time = time.time()

        while responses_received < requests_sent:
            try:
                data = client_socket.recv(4096).decode('utf-8')
                if not data:
                    break
                buffer += data

                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    response = line.strip()

                    if response:
                        responses_received += 1

                        if responses_received % 100 == 0:
                            elapsed = time.time() - start_read_time
                           

                        if self.process_response(response, word_list):
                            return

            except:
                break

        read_time = time.time() - start_read_time
       

    def process_response(self, response, word_list):
       
        if "EOF" in response:
            if response != "EOF":
                words = response.replace(",EOF", "").split(',')
                valid_words = [w.strip() for w in words if w.strip()]
                word_list.extend(valid_words)
            return True  
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
