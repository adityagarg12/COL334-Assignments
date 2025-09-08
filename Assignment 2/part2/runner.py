import socket
import sys
import time
import json
from collections import defaultdict
from typing import Dict

class Config:
    def __init__(self, config_file="config.json"):
        with open(config_file) as f:
            cfg = json.load(f)
        self.server_ip = cfg["server_ip"]
        self.server_port = cfg["server_port"]
        self.k = cfg["k"]
        self.p = cfg["p"]
        self.filename = cfg["filename"]
        self.num_clients = cfg.get("num_clients", 1)
        self.c = cfg.get("c", 1)  # number of back-to-back requests for greedy client

class WordClient:
    def __init__(self, greedy=False):
        self.config = Config()
        self.greedy = greedy

    def parse_response(self, response: str) -> list:
        words = []
        if response.strip():
            word_list = response.strip().split(',')
            for word in word_list:
                if word and word != "EOF":
                    words.append(word.strip())
        return words

    def run_normal(self) -> Dict[str, int]:
        """Original sequential client"""
        total_word_frequency = defaultdict(int)
        current_offset = self.config.p
        eof_reached = False

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((self.config.server_ip, self.config.server_port))
            while not eof_reached:
                request = f"{current_offset},{self.config.k}\n"
                client_socket.send(request.encode())
                response = client_socket.recv(1024).decode()

                if response.strip() == "EOF":
                    eof_reached = True
                else:
                    words = self.parse_response(response)
                    for w in words:
                        total_word_frequency[w] += 1
                    current_offset += len(words)
                    if "EOF" in response:
                        eof_reached = True
        return total_word_frequency

    def run_greedy(self) -> Dict[str, int]:
      
        total_word_frequency = defaultdict(int)
        current_offset = self.config.p

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((self.config.server_ip, self.config.server_port))

            # send c requests without waiting
            for i in range(self.config.c):
                req = f"{current_offset},{self.config.k}\n"
                client_socket.send(req.encode())
                current_offset += self.config.k

            # now collect responses
            while True:
                response = client_socket.recv(1024).decode()
                if not response:
                    break
                if response.strip() == "EOF":
                    break
                words = self.parse_response(response)
                for w in words:
                    total_word_frequency[w] += 1
                if "EOF" in response:
                    break

        return total_word_frequency

    def run(self):
        start = time.time()
        if self.greedy:
            freqs = self.run_greedy()
        else:
            freqs = self.run_normal()
        end = time.time()
        return freqs, end - start

def main():

    greedy = (len(sys.argv) > 1 and sys.argv[1] == "greedy")
    client = WordClient(greedy=greedy)
    freqs, t = client.run()
    print(f"Completion time: {t:.4f}s, Greedy={greedy}")

if __name__ == "__main__":
    main()
