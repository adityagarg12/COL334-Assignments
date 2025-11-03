import socket
import sys
import time
import struct

# Constants
MAX_PAYLOAD = 1200
HEADER_SIZE = 20
DATA_SIZE = MAX_PAYLOAD - HEADER_SIZE
EOF_MARKER = b"EOF"
REQUEST_RETRIES = 5
REQUEST_TIMEOUT = 2.0

class ReceiverState:
    def __init__(self):
        self.next_expected_seq = 0  # Next byte we expect in order
        self.received_data = {}  # seq_num -> data (out-of-order buffer)
        self.received_ranges = []  # List of (start, end) tuples for SACK
        
    def add_packet(self, seq_num, data):
        """Add received packet and update state"""
        if seq_num in self.received_data:
            return  # Duplicate
        
        self.received_data[seq_num] = data
        
        # Update received ranges for SACK
        self._update_ranges(seq_num, seq_num + len(data))
    
    def _update_ranges(self, start, end):
        """Update received ranges, merging overlapping ranges"""
        new_ranges = []
        merged = False
        
        for r_start, r_end in self.received_ranges:
            if end < r_start or start > r_end:
                # No overlap
                new_ranges.append((r_start, r_end))
            else:
                # Overlap or adjacent - merge
                start = min(start, r_start)
                end = max(end, r_end)
                merged = True
        
        new_ranges.append((start, end))
        new_ranges.sort()
        
        # Merge adjacent ranges
        final_ranges = []
        for r_start, r_end in new_ranges:
            if final_ranges and r_start <= final_ranges[-1][1]:
                # Merge with previous
                final_ranges[-1] = (final_ranges[-1][0], max(final_ranges[-1][1], r_end))
            else:
                final_ranges.append((r_start, r_end))
        
        self.received_ranges = final_ranges
    
    def get_sack_blocks(self):
        """Get up to 2 SACK blocks that don't include cumulative ACK range"""
        sack_blocks = []
        
        for start, end in self.received_ranges:
            if start >= self.next_expected_seq:
                sack_blocks.append((start, end))
                if len(sack_blocks) == 2:
                    break
        
        return sack_blocks

def create_ack_packet(ack_num, sack_blocks):
    """Create ACK packet: [ack_num (4B)] [SACK blocks (16B)]"""
    header = struct.pack('!I', ack_num)
    
    # Add SACK blocks (up to 2)
    sack_data = b''
    for i in range(2):
        if i < len(sack_blocks):
            start, end = sack_blocks[i]
            sack_data += struct.pack('!II', start, end)
        else:
            sack_data += b'\x00' * 8
    
    return header + sack_data

def parse_packet(data):
    """Parse received packet: [seq_num (4B)] [reserved (16B)] [data]"""
    if len(data) < HEADER_SIZE:
        return None, None
    
    seq_num = struct.unpack('!I', data[:4])[0]
    payload = data[HEADER_SIZE:]
    
    return seq_num, payload

def send_request_with_retry(sock, server_addr):
    """Send file request with retries"""
    request_msg = b'\x01'  # Single byte request
    
    for attempt in range(REQUEST_RETRIES):
        sock.sendto(request_msg, server_addr)
        
        # Wait for first data packet as confirmation
        sock.settimeout(REQUEST_TIMEOUT)
        try:
            data, _ = sock.recvfrom(MAX_PAYLOAD)
            return data  # Return first packet
        except socket.timeout:
            continue
    
    sys.exit(1)

def receive_file(sock, server_addr):
    """Receive file using sliding window protocol"""
    state = ReceiverState()
    output_file = open('received_data.txt', 'wb')
    
    print("Starting file reception...")
    start_time = time.time()
    
    # Send initial request and get first packet
    first_packet = send_request_with_retry(sock, server_addr)
    
    # Process first packet
    seq_num, payload = parse_packet(first_packet)
    if seq_num is not None:
        if payload == EOF_MARKER:
            # Empty file case
            ack_packet = create_ack_packet(seq_num + len(payload), [])
            sock.sendto(ack_packet, server_addr)
            output_file.close()
            return
        
        state.add_packet(seq_num, payload)
        
        # Write contiguous data to file (including first packet)
        while state.next_expected_seq in state.received_data:
            data_to_write = state.received_data.pop(state.next_expected_seq)
            output_file.write(data_to_write)
            state.next_expected_seq += len(data_to_write)
    
    # Send ACK for first packet
    sack_blocks = state.get_sack_blocks()
    ack_packet = create_ack_packet(state.next_expected_seq, sack_blocks)
    sock.sendto(ack_packet, server_addr)
    
    # Set socket to non-blocking for efficient receiving
    sock.settimeout(0.01)
    
    eof_received = False
    last_ack_time = time.time()
    
    while not eof_received:
        try:
            data, _ = sock.recvfrom(MAX_PAYLOAD)
            seq_num, payload = parse_packet(data)
            
            if seq_num is None:
                continue
            
            # Check for EOF
            if payload == EOF_MARKER:
                eof_received = True
                
                # Send final ACK for EOF
                ack_packet = create_ack_packet(seq_num + len(payload), [])
                sock.sendto(ack_packet, server_addr)
                
                # Send a few more ACKs to ensure server receives it
                for _ in range(3):
                    time.sleep(0.05)
                    sock.sendto(ack_packet, server_addr)
                
                break
            
            # Add packet to buffer
            state.add_packet(seq_num, payload)
            
            # Write contiguous data to file
            while state.next_expected_seq in state.received_data:
                data_to_write = state.received_data.pop(state.next_expected_seq)
                output_file.write(data_to_write)
                state.next_expected_seq += len(data_to_write)
            
            # Send ACK immediately
            sack_blocks = state.get_sack_blocks()
            ack_packet = create_ack_packet(state.next_expected_seq, sack_blocks)
            sock.sendto(ack_packet, server_addr)
            last_ack_time = time.time()
            
        except socket.timeout:
            # Periodically resend ACK in case it was lost
            current_time = time.time()
            if current_time - last_ack_time > 0.08:
                sack_blocks = state.get_sack_blocks()
                ack_packet = create_ack_packet(state.next_expected_seq, sack_blocks)
                sock.sendto(ack_packet, server_addr)
                last_ack_time = current_time
            continue
        except BlockingIOError:
            continue
    
    output_file.close()
    
    elapsed = time.time() - start_time
    bytes_received = state.next_expected_seq
    print(f"Transfer complete: {bytes_received} bytes in {elapsed:.2f}s")

def main():
    # Default values
    DEFAULT_SERVER_IP = "127.0.0.1"
    DEFAULT_SERVER_PORT = 8080
    
    if len(sys.argv) == 3:
        server_ip = sys.argv[1]
        server_port = int(sys.argv[2])
    elif len(sys.argv) == 1:
        # Use defaults
        server_ip = DEFAULT_SERVER_IP
        server_port = DEFAULT_SERVER_PORT
        print(f"Using default values: IP={server_ip}, PORT={server_port}")
    else:
        print("Usage: python3 p1_client.py [<SERVER_IP> <SERVER_PORT>]")
        print(f"If no arguments provided, defaults to IP={DEFAULT_SERVER_IP}, PORT={DEFAULT_SERVER_PORT}")
        sys.exit(1)
    
    # Create socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_addr = (server_ip, server_port)
    
    # Receive file
    receive_file(sock, server_addr)
    
    # Close
    sock.close()

if __name__ == "__main__":
    main()