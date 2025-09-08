#!/usr/bin/env python3
# server.py -- Round-Robin central scheduler

import socket
import threading
# import json
import time
import collections

class RoundRobinServer:
    def __init__(self, config_file="config.json"):
        self.config = self.load_config(config_file)
        self.words = []
        self.load_words_from_file()
        self.server_socket = None

       
        self.clients = {}
        self.clients_lock = threading.Lock()
        self.client_order = []  # order for round-robin (list of client_ids)
        self.next_index = 0

        
        self.processing_delay = 0.0 

    def load_config(self, config_file: str) -> dict:
        config = {
            "server_ip": "0.0.0.0",
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
        try:
            filename = self.config.get("filename", "words.txt")
            with open(filename, "r") as f:
                content = f.read().strip()
                self.words = [w.strip() for w in content.split(",") if w.strip()]
        except Exception as e:
            print(f"Could not load {filename}:", e)
            self.words = []

    def process_request(self, request: str):

        try:
            parts = request.strip().split(",")
            if len(parts) != 2:
                return "Invalid request"
            p = int(parts[0])
            k = int(parts[1])
        except:
            return "Invalid request"

        if p >= len(self.words):
            return "EOF"

        take = min(k, len(self.words) - p)
        resp = ",".join(self.words[p:p+take])
        if p + k >= len(self.words):
            resp += ",EOF"
        return resp

    def client_reader(self, client_sock, address, client_id):
       
        thread_name = threading.current_thread().name
        
        buff = ""
        try:
            while True:
                data = client_sock.recv(4096)
                if not data:
                    break
                buff += data.decode('utf-8')
                while '\n' in buff:
                    line, buff = buff.split('\n', 1)
                    if not line.strip():
                        continue
                    with self.clients_lock:
                        entry = self.clients.get(client_id)
                        if entry and entry['alive']:
                            entry['queue'].append(line.strip())
                        else:
                        
                            pass
        except Exception as e:
            print(f"[{thread_name}] Read error {client_id}: {e}")
        finally:
            # mark client dead; processor will clean socket
            with self.clients_lock:
                entry = self.clients.get(client_id)
                if entry:
                    entry['alive'] = False
            

    def rr_processor(self):
      
        thread_name = threading.current_thread().name
       

        while True:
            with self.clients_lock:
                alive_clients = [cid for cid in self.client_order if cid in self.clients and self.clients[cid]['alive'] or (cid in self.clients and len(self.clients[cid]['queue'])>0)]
                # reorder client_order: remove dead ones
                if set(alive_clients) != set(self.client_order):
                    self.client_order = [c for c in self.client_order if c in alive_clients]

                if not self.client_order:
                    # no clients currently: sleep and continue
                    pass

                # pick next client index safely
                if self.client_order:
                    if self.next_index >= len(self.client_order):
                        self.next_index = 0
                    client_id = self.client_order[self.next_index]
                else:
                    client_id = None

            if client_id is None:
                time.sleep(0.01)
                continue

            # serve at most one request for this client
            served = False
            with self.clients_lock:
                entry = self.clients.get(client_id)
                if entry and len(entry['queue']) > 0:
                    request = entry['queue'].popleft()
                    sock = entry['sock']
                    served = True
                else:
                    request = None
                    sock = None

            if served and request is not None:
                # optional small delay to exaggerate scheduling
                if self.processing_delay:
                    time.sleep(self.processing_delay)

                try:
                    response = self.process_request(request)
                    to_send = response + "\n"
                    try:
                        sock.sendall(to_send.encode('utf-8'))
                    except Exception:
                        pass

                    if "EOF" in response:
                        # close and cleanup this client
                        with self.clients_lock:
                            entry = self.clients.get(client_id)
                            if entry:
                                try:
                                    entry['sock'].shutdown(socket.SHUT_RDWR)
                                    entry['sock'].close()
                                except:
                                    pass
                                entry['alive'] = False
                                # we will remove from client_order on next loop
                except Exception as e:
                    print(f"[{thread_name}] Error processing {client_id}: {e}")

                # advance rr pointer to next client
                with self.clients_lock:
                    self.next_index += 1
                    if self.next_index >= max(1, len(self.client_order)):
                        self.next_index = 0
                continue

            # if we didn't serve (no queued request for this client), advance pointer
            with self.clients_lock:
                self.next_index += 1
                if self.next_index >= max(1, len(self.client_order)):
                    self.next_index = 0

            # if nobody had anything, sleep a bit to avoid busy-spin
            time.sleep(0.001)

    def start_server(self):
        ip = self.config.get('server_ip', '0.0.0.0')
        port = self.config.get('server_port', 5000)

        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((ip, port))
        self.server_socket.listen(50)
        print(f"RR Server listening on {ip}:{port}")

        # start processor thread
        proc = threading.Thread(target=self.rr_processor, name="RR-Processor", daemon=True)
        proc.start()

        client_idx = 0
        try:
            while True:
                client_sock, address = self.server_socket.accept()
                client_idx += 1
                client_id = f"C{client_idx}"
                print(f"New client {client_id} from {address}")

                with self.clients_lock:
                    self.clients[client_id] = {'sock': client_sock, 'queue': collections.deque(), 'alive': True}
                    self.client_order.append(client_id)

                reader = threading.Thread(target=self.client_reader, args=(client_sock, address, client_id),
                                          name=f"Reader-{client_id}", daemon=True)
                reader.start()
        except KeyboardInterrupt:
            print("Shutting down server...")
        finally:
            try:
                self.server_socket.close()
            except:
                pass

if __name__ == "__main__":
    server = RoundRobinServer()
    server.start_server()
