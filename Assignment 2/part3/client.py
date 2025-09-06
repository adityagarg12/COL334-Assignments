import socket
import json
import time
import sys

def run_client(client_id, is_greedy=False):
    """
    Initializes a client, connects to the server, and downloads the word list.
    Logs its own completion time.

    Args:
        client_id (int): A unique identifier for the client.
        is_greedy (bool): If True, the client sends 'c' requests back-to-back.
    """
    with open('config.json', 'r') as f:
        config = json.load(f)

    server_ip = config['server_ip']
    server_port = config['server_port']
    k = config['k']
    c = config.get('c', 1) # Number of requests for the greedy client

    # Create a TCP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Connect to the server
        client_socket.connect((server_ip, server_port))
        print(f"Client {client_id} connected to server at {server_ip}:{server_port}")

        full_word_list = []
        offset = 0
        start_time = time.time()

        if is_greedy:
            print(f"Client {client_id} (Greedy) starting to send {c} requests...")
            # Send 'c' requests back-to-back
            for _ in range(c):
                num_requests_to_make = 0
                while True:
                    request = f"{offset},{k}\n"
                    client_socket.sendall(request.encode('utf-8'))
                    num_requests_to_make += 1
                    
                    response = client_socket.recv(4096).decode('utf-8').strip()
                    if "EOF" in response:
                        words = response.replace(",EOF", "").split(',')
                        if words and words[0]: # handle empty response before EOF
                           full_word_list.extend(words)
                        break
                    else:
                        full_word_list.extend(response.split(','))
                    offset += k
                
                # Reset for the next full file download request in the burst
                offset = 0
                full_word_list = []

        else: # Normal client
            while True:
                request = f"{offset},{k}\n"
                client_socket.sendall(request.encode('utf-8'))
                
                response = client_socket.recv(4096).decode('utf-8').strip()

                if "EOF" in response:
                    words = response.replace(",EOF", "").split(',')
                    if words and words[0]:
                        full_word_list.extend(words)
                    break
                else:
                    full_word_list.extend(response.split(','))
                
                offset += k
        
        end_time = time.time()
        completion_time = end_time - start_time
        
        print(f"Client {client_id} finished in {completion_time:.4f} seconds.")

        # Log completion time to a file
        with open(f"part3_results/client_{client_id}_time.txt", "w") as f:
            f.write(str(completion_time))

    except Exception as e:
        print(f"Client {client_id} Error: {e}")
    finally:
        client_socket.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 client.py <client_id> [--greedy]")
        sys.exit(1)
    
    client_id = int(sys.argv[1])
    greedy_flag = len(sys.argv) > 2 and sys.argv[2] == '--greedy'
    
    run_client(client_id, greedy_flag)