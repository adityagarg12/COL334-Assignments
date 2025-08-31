import socket
import sys
import time
from collections import defaultdict
from typing import Dict

class Config:
    def __init__(self):
        self.server_ip = ""
        self.server_port = 0
        self.k = 0
        self.p = 0
        self.filename = ""

class WordClient:
    def __init__(self, config_file: str = "config.json"):
        """Initialize the client with configuration."""
        self.config = self.load_config(config_file)
        
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
                
                elif '"k"' in line:
                    colon_pos = line.find(':')
                    if colon_pos != -1:
                        num_str = line[colon_pos + 1:]
                        clean_num = ""
                        for c in num_str:
                            if c.isdigit():
                                clean_num += c
                        if clean_num:
                            config.k = int(clean_num)
                
                elif '"p"' in line:
                    colon_pos = line.find(':')
                    if colon_pos != -1:
                        num_str = line[colon_pos + 1:]
                        clean_num = ""
                        for c in num_str:
                            if c.isdigit():
                                clean_num += c
                        if clean_num:
                            config.p = int(clean_num)
                
                elif '"filename"' in line:
                    colon_pos = line.find(':')
                    if colon_pos != -1:
                        quote_start = line.find('"', colon_pos)
                        if quote_start != -1:
                            quote_end = line.find('"', quote_start + 1)
                            if quote_end != -1:
                                config.filename = line[quote_start + 1:quote_end]
            
            print("Client Configuration:")
            print(f"Server IP: {config.server_ip}")
            print(f"Server Port: {config.server_port}")
            print(f"Request: p={config.p}, k={config.k}")
            print(f"File: {config.filename}")
            print()
            return config
            
        except FileNotFoundError:
            print(f"Failed to open config file: {config_file}")
            sys.exit(1)
        except Exception as e:
            print(f"Error parsing config file: {e}")
            sys.exit(1)
    
    def parse_response(self, response: str) -> list:
        """Parse the server response and extract words."""
        words = []
        if response.strip():
            word_list = response.strip().split(',')
            for word in word_list:
                if word and word != "EOF":
                    words.append(word)
        return words
    
    def display_word_frequencies(self, word_frequency: Dict[str, int]):
        """Display the word frequencies."""
        print("\n=== Word Frequencies ===")
        if not word_frequency:
            print("No words received.")
        else:
            for word, count in word_frequency.items():
                print(f"{word}, {count}")
    
    def connect_and_request(self) -> Dict[str, int]:
        """Connect to server, send single request, get response, and disconnect."""
        word_frequency = defaultdict(int)
        
        try:
            # Create socket
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            print("Socket created successfully")
            
            # Connect to server
            client_socket.connect((self.config.server_ip, self.config.server_port))
            print("Connected to server successfully!")
            
            # Send request in format "p,k\n"
            request = f"{self.config.p},{self.config.k}\n"
            print(f"Sending request: {request.strip()}")
            client_socket.send(request.encode('utf-8'))
            
            # Receive response
            response = client_socket.recv(1024).decode('utf-8')
            print(f"Received response: {response.strip()}")
            
            # Parse and count word frequencies
            if response.strip() == "EOF":
                print("Request offset is beyond file size - no words received.")
            elif "EOF" in response:
                print("End of file reached in response.")
                words = self.parse_response(response)
                print(f"Received {len(words)} words: {' '.join(words[:10])}" + ("..." if len(words) > 10 else ""))
                for word in words:
                    word_frequency[word] += 1
            else:
                # Normal response - parse all words
                words = self.parse_response(response)
                print(f"Received {len(words)} words: {' '.join(words[:10])}" + ("..." if len(words) > 10 else ""))
                for word in words:
                    word_frequency[word] += 1
            
        except ConnectionRefusedError:
            print("Connection to server failed - server may not be running")
            return {}
        except Exception as e:
            print(f"Client error: {e}")
            return {}
        finally:
            try:
                client_socket.close()
                print("Connection closed.")
            except:
                pass
        
        return dict(word_frequency)
    
    def run(self) -> tuple:
        """Run the client and return word frequencies and completion time."""
        start_time = time.time()
        word_frequencies = self.connect_and_request()
        end_time = time.time()
        
        # Display results
        self.display_word_frequencies(word_frequencies)
        
        completion_time = end_time - start_time
        print(f"\nCompletion time: {completion_time:.4f} seconds")
        
        return word_frequencies, completion_time

def main():
    """Main function to run a single client."""
    client = WordClient()
    client.run()

if __name__ == "__main__":
    main()
