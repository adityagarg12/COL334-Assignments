import socket
import sys
import time
import struct
import os

# Constants
MAX_PAYLOAD = 1200
HEADER_SIZE = 20
DATA_SIZE = MAX_PAYLOAD - HEADER_SIZE  # 1180 bytes
EOF_MARKER = b"EOF"
INITIAL_RTO = 0.5  # Initial Retransmission Timeout in seconds
ALPHA = 0.125  # RTT smoothing factor
BETA = 0.25    # RTT deviation factor

class Packet:
    def __init__(self, seq_num, data):
        self.seq_num = seq_num
        self.data = data
        self.send_time = None
        
    def to_bytes(self):
        # Header: [seq_num (4B)] [SACK blocks (16B)] [data]
        header = struct.pack('!I', self.seq_num) + b'\x00' * 16
        return header + self.data

class ServerState:
    def __init__(self, sws):
        self.sws = sws  # Sender window size in bytes
        self.send_base = 0  # Next byte expecting ACK for
        self.next_seq_num = 0  # Next byte to send
        self.packets = {}  # seq_num -> Packet
        self.rto = INITIAL_RTO
        self.estimated_rtt = None
        self.dev_rtt = 0
        self.dup_ack_count = {}  # ACK number -> count
        self.last_ack_received = -1
        self.sack_retransmitted = set()
        
        
    def update_rtt(self, sample_rtt):
        """Update RTO using TCP-like algorithm"""
        if self.estimated_rtt is None:
            self.estimated_rtt = sample_rtt
            self.dev_rtt = sample_rtt / 2
        else:
            self.dev_rtt = (1 - BETA) * self.dev_rtt + BETA * abs(sample_rtt - self.estimated_rtt)
            self.estimated_rtt = (1 - ALPHA) * self.estimated_rtt + ALPHA * sample_rtt
        
        self.rto = self.estimated_rtt + 4 * self.dev_rtt
        self.rto = max(0.2, min(self.rto, 1.5)) # Clamp RTO between 200ms and 1500ms

def parse_ack(data):
    """Parse ACK packet: [ack_num (4B)] [SACK blocks (16B)]"""
    if len(data) < 20:
        return None, []
    
    ack_num = struct.unpack('!I', data[:4])[0]
    
    # Parse SACK blocks (2 blocks max, each 8 bytes)
    sack_blocks = []
    for i in range(2):
        offset = 4 + i * 8
        if offset + 8 <= len(data):
            block_data = data[offset:offset + 8]
            if block_data != b'\x00' * 8:  # Non-zero SACK block
                start, end = struct.unpack('!II', block_data)
                if start != 0 or end != 0:
                    sack_blocks.append((start, end))
    
    return ack_num, sack_blocks

def send_file(sock, client_addr, file_data, sws):
    """Send file using sliding window protocol"""
    state = ServerState(sws)
    file_size = len(file_data)
    all_data_sent = False
    eof_sent = False
    eof_acked = False
    
    print(f"Starting file transfer: {file_size} bytes")
    start_time = time.time()
    
    # Set socket to non-blocking for efficient handling
    sock.settimeout(0.01)
    
    while not eof_acked:
        current_time = time.time()
        
        # Send new packets within window
        while (state.next_seq_num < state.send_base + state.sws and 
               not all_data_sent):
            
            if state.next_seq_num >= file_size:
                all_data_sent = True
                break
            
            # Create and send packet
            end_byte = min(state.next_seq_num + DATA_SIZE, file_size)
            data_chunk = file_data[state.next_seq_num:end_byte]
            
            packet = Packet(state.next_seq_num, data_chunk)
            packet.send_time = current_time
            
            sock.sendto(packet.to_bytes(), client_addr)
            state.packets[state.next_seq_num] = packet
            
            state.next_seq_num = end_byte
        
        # Send EOF if all data sent and not yet sent EOF
        if all_data_sent and not eof_sent and state.send_base >= file_size:
            eof_packet = Packet(file_size, EOF_MARKER)
            eof_packet.send_time = current_time
            sock.sendto(eof_packet.to_bytes(), client_addr)
            state.packets[file_size] = eof_packet
            eof_sent = True
            print("EOF sent")
        
        # Check for timeouts
        for seq_num, packet in list(state.packets.items()):
            if current_time - packet.send_time > state.rto:
                # Timeout - retransmit
                packet.send_time = current_time
                sock.sendto(packet.to_bytes(), client_addr)
                print(f"Timeout retransmit: seq={seq_num}")
        
        # Receive ACKs
        try:
            ack_data, _ = sock.recvfrom(MAX_PAYLOAD)
            ack_num, sack_blocks = parse_ack(ack_data)
            
            if ack_num is None:
                continue
            
            # Check if this is EOF ACK
            if eof_sent and ack_num > file_size:
                eof_acked = True
                print("EOF acknowledged")
                break
            
            # Update RTT if this ACKs new data
            if ack_num > state.send_base:
                if state.send_base in state.packets:
                    sample_rtt = current_time - state.packets[state.send_base].send_time
                    state.update_rtt(sample_rtt)
                
                # Cumulative ACK - remove all packets up to ack_num
                for seq in list(state.packets.keys()):
                    if seq < ack_num:
                        del state.packets[seq]
                
                state.send_base = ack_num
                state.dup_ack_count.clear()
                state.last_ack_received = ack_num
                
            elif ack_num == state.send_base and ack_num == state.last_ack_received:
                # Duplicate ACK
                state.dup_ack_count[ack_num] = state.dup_ack_count.get(ack_num, 0) + 1
                
                # Fast retransmit on 3 duplicate ACKs
                if state.dup_ack_count[ack_num] == 3:
                    if state.send_base in state.packets:
                        packet = state.packets[state.send_base]
                        packet.send_time = current_time
                        sock.sendto(packet.to_bytes(), client_addr)
                        print(f"Fast retransmit: seq={state.send_base}")
            
            for start, end in sack_blocks:
                # Remove SACKed packets
                for seq in list(state.packets.keys()):
                    if start <= seq < end:
                        if seq in state.packets:
                            del state.packets[seq]
                            # Clear from retransmit tracking when ACKed
                            state.sack_retransmitted.discard(seq)
            
            # SACK-based proactive retransmission: detect and retransmit holes
            if sack_blocks and ack_num == state.send_base:  # Only if cumulative ACK hasn't moved
                # Find the minimum hole between send_base and first SACK block
                first_sack_start = min(block[0] for block in sack_blocks)
                
                # If there's a gap between send_base and first SACK block, retransmit it ONCE
                if first_sack_start > state.send_base:
                    if state.send_base in state.packets and state.send_base not in state.sack_retransmitted:
                        packet = state.packets[state.send_base]
                        packet.send_time = current_time
                        sock.sendto(packet.to_bytes(), client_addr)
                        state.sack_retransmitted.add(state.send_base)
                        print(f"SACK-triggered retransmit: seq={state.send_base}")
            
            state.last_ack_received = ack_num
            
        except socket.timeout:
            continue
        except BlockingIOError:
            continue
    
    elapsed = time.time() - start_time
    throughput = file_size / elapsed / 1024 / 1024  # MB/s
    print(f"Transfer complete: {file_size} bytes in {elapsed:.2f}s ({throughput:.2f} MB/s)")

def main():
    # Default values
    DEFAULT_SERVER_IP = "127.0.0.1"
    DEFAULT_SERVER_PORT = 8080
    DEFAULT_SWS = 5000  # 10KB default window size
    
    if len(sys.argv) == 4:
        server_ip = sys.argv[1]
        server_port = int(sys.argv[2])
        sws = int(sys.argv[3])
    elif len(sys.argv) == 1:
        # Use defaults
        server_ip = DEFAULT_SERVER_IP
        server_port = DEFAULT_SERVER_PORT
        sws = DEFAULT_SWS
        print(f"Using default values: IP={server_ip}, PORT={server_port}, SWS={sws}")
    else:
        print("Usage: python3 p1_server.py [<SERVER_IP> <SERVER_PORT> <SWS>]")
        print(f"If no arguments provided, defaults to IP={DEFAULT_SERVER_IP}, PORT={DEFAULT_SERVER_PORT}, SWS={DEFAULT_SWS}")
        sys.exit(1)
    
    # Read file
    if not os.path.exists('data.txt'):
        print("Error: data.txt not found")
        sys.exit(1)
    
    with open('data.txt', 'rb') as f:
        file_data = f.read()
    
    if len(file_data) == 0:
        print("Warning: data.txt is empty")
    
    # Create socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((server_ip, server_port))
    
    print(f"Server listening on {server_ip}:{server_port}")
    print(f"Sender window size: {sws} bytes")
    print(f"File size: {len(file_data)} bytes")
    
    # Wait for client request (with retries)
    sock.settimeout(None)
    request, client_addr = sock.recvfrom(MAX_PAYLOAD)
    print(f"Received request from {client_addr}")
    
    # Send file
    send_file(sock, client_addr, file_data, sws)
    
    # Close
    sock.close()
    print("Server terminated")

if __name__ == "__main__":
    main()