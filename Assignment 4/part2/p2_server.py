import socket
import sys
import time
import struct
import os
import math

# Constants
MAX_PAYLOAD = 1200
HEADER_SIZE = 20
DATA_SIZE = MAX_PAYLOAD - HEADER_SIZE  # 1180 bytes
EOF_MARKER = b"EOF"
INITIAL_RTO = 0.3
ALPHA = 0.125  # RTT smoothing factor
BETA = 0.25    # RTT deviation factor

# Congestion Control Constants  
MSS = 1200  # Maximum Segment Size in bytes
INITIAL_CWND = 10 * MSS  # Start conservative to avoid initial congestion
INITIAL_SSTHRESH = 1000000  # Very large initial threshold
CUBIC_C = 0.5  # Higher CUBIC constant for faster growth
CUBIC_BETA = 0.95  # Very mild decrease (keep cwnd high!)
MIN_CWND = 1 * MSS


class CongestionControl:
    """
    CUBIC-Fair Hybrid Congestion Control Algorithm
    Optimized for high JFI × Link Utilization score
    """
    
    def __init__(self):
        self.cwnd = INITIAL_CWND
        self.ssthresh = INITIAL_SSTHRESH
        
        # CUBIC state
        self.wmax = 0  # Window size before last reduction
        self.epoch_start = 0  # Time when current epoch started
        self.origin_point = 0  # Origin point K
        self.d_min = float('inf')  # Minimum RTT observed
        self.w_tcp = 0  # TCP-friendly window
        self.ack_count = 0  # Number of ACKs received in current RTT
        
        # Fast convergence
        self.w_last_max = 0  # Previous Wmax for fast convergence
        
        # State tracking
        self.in_slow_start = True
        self.in_fast_recovery = False
        
        # RTT tracking for CUBIC
        self.rtt_samples = []
        self.current_rtt = 0.04  # Initial estimate: 40ms
        
    def update_rtt(self, rtt_sample):
        """Update RTT estimate"""
        self.current_rtt = rtt_sample
        self.rtt_samples.append(rtt_sample)
        
        # Keep only recent samples
        if len(self.rtt_samples) > 20:
            self.rtt_samples.pop(0)
        
        # Update minimum RTT
        if rtt_sample < self.d_min:
            self.d_min = rtt_sample
    
    def on_ack_received(self, bytes_acked, current_time):
        """
        Handle ACK reception - increase cwnd
        Returns: new cwnd value
        """
        if self.in_fast_recovery:
            # Inflate window during fast recovery
            self.cwnd += MSS
            return self.cwnd
        
        if self.in_slow_start:
            # Slow start: exponential growth
            self.cwnd += bytes_acked
            
            # Exit slow start if we hit ssthresh
            if self.cwnd >= self.ssthresh:
                self.in_slow_start = False
                self.epoch_start = current_time
        else:
            # Congestion avoidance: CUBIC growth
            self._cubic_update(current_time)
        
        return self.cwnd
    
    def _cubic_update(self, current_time):
        """CUBIC congestion avoidance"""
        self.ack_count += 1
        
        if self.epoch_start == 0:
            self.epoch_start = current_time
            self.ack_count = 1
            self.w_tcp = self.cwnd
            
            if self.wmax == 0:
                self.wmax = self.cwnd
            else:
                # Fast Convergence: if cwnd < wmax, reduce wmax more
                if self.cwnd < self.wmax:
                    self.w_last_max = self.wmax
                    self.wmax = self.cwnd * (2.0 - CUBIC_BETA) / 2.0
                else:
                    self.w_last_max = self.wmax
            
            # Calculate K (time to reach Wmax)
            self.origin_point = self.wmax
            K_cubic = math.pow(abs(self.wmax - self.cwnd) / (CUBIC_C * MSS), 1.0/3.0)
            self.origin_point = self.wmax
        
        # Time since epoch start
        t = current_time - self.epoch_start + self.current_rtt
        
        # CUBIC window calculation
        K = math.pow(abs(self.origin_point - self.cwnd) / (CUBIC_C * MSS), 1.0/3.0)
        target = self.origin_point + CUBIC_C * math.pow(t - K, 3) * MSS
        
        # TCP-friendly window
        # Very aggressive: grow much faster than standard TCP
        self.w_tcp += (4.0 * CUBIC_BETA / (2.0 - CUBIC_BETA)) * (MSS * MSS / self.cwnd)
        
        # Use max of CUBIC and TCP-friendly
        if target < self.cwnd:
            target = self.cwnd
        
        w_cubic = target
        
        # Take max for aggressiveness
        if w_cubic < self.w_tcp:
            # TCP mode
            w_target = self.w_tcp
        else:
            # CUBIC mode
            w_target = w_cubic
        
        # Update cwnd based on ACK count (every 1/3 RTT for very fast growth)
        if self.ack_count >= max(1, int(self.cwnd / (3 * MSS))):
            delta = (w_target - self.cwnd) / self.cwnd * MSS
            increment = max(delta, 3 * MSS / self.cwnd)  # At least 3 bytes per ACK
            self.cwnd += increment
            self.ack_count = 0
    
    def on_timeout(self, recent_progress=False):
        """
        Handle timeout - severity depends on whether we're making progress
        Returns: new cwnd value
        """
        # Set ssthresh to reduced window
        self.ssthresh = max(int(self.cwnd * CUBIC_BETA), 2 * MSS)
        
        if recent_progress:
            # We got ACKs recently, this is probably just one lost packet
            # Reduce cwnd but don't reset to 1 MSS
            self.cwnd = self.ssthresh
            self.in_slow_start = False  # Stay in CA
        else:
            # No recent progress, real congestion
            # Reset to 1 MSS and re-enter slow start
            self.cwnd = 1 * MSS
            self.in_slow_start = True
        
        self.in_fast_recovery = False
        
        # Reset CUBIC state
        self.epoch_start = 0
        self.w_tcp = 0
        self.ack_count = 0
        self.wmax = 0
        
        return self.cwnd
    
    def on_fast_retransmit(self):
        """
        Handle 3 duplicate ACKs - mild congestion
        Returns: new cwnd value
        """
        if self.in_fast_recovery:
            return self.cwnd
        
        # Save wmax before reduction
        self.wmax = self.cwnd
        
        # Multiplicative decrease
        self.ssthresh = max(int(self.cwnd * CUBIC_BETA), 2 * MSS)
        self.cwnd = self.ssthresh + 3 * MSS
        
        self.in_slow_start = False
        self.in_fast_recovery = True
        
        # Reset CUBIC epoch
        self.epoch_start = 0
        self.w_tcp = 0
        self.ack_count = 0
        
        return self.cwnd
    
    def exit_fast_recovery(self):
        """Exit fast recovery mode"""
        self.in_fast_recovery = False
        self.cwnd = self.ssthresh
    
    def get_cwnd(self):
        """Get current congestion window size"""
        return max(self.cwnd, MIN_CWND)


class Packet:
    def __init__(self, seq_num, data):
        self.seq_num = seq_num
        self.data = data
        self.send_time = None
        
    def to_bytes(self):
        # Header: [seq_num (4B)] [reserved (16B)] [data]
        header = struct.pack('!I', self.seq_num) + b'\x00' * 16
        return header + self.data


class ServerState:
    def __init__(self):
        # Congestion control
        self.cc = CongestionControl()
        
        # Reliability state (from Part 1)
        self.send_base = 0
        self.next_seq_num = 0
        self.packets = {}
        self.rto = INITIAL_RTO
        self.estimated_rtt = None
        self.dev_rtt = 0
        self.dup_ack_count = {}
        self.last_ack_received = -1
        self.sack_retransmitted = set()
        self.sack_hole_count = {}
        self.sack_hole_first_seen = {}
        
        # Timeout cascade prevention
        self.last_timeout_time = 0
        self.timeout_triggered_this_window = False
        
        # Track progress for smart timeout handling
        self.last_progress_time = 0
        
    def update_rtt(self, sample_rtt):
        """Update RTO using TCP-like algorithm"""
        if self.estimated_rtt is None:
            self.estimated_rtt = sample_rtt
            self.dev_rtt = sample_rtt / 2
        else:
            self.dev_rtt = (1 - BETA) * self.dev_rtt + BETA * abs(sample_rtt - self.estimated_rtt)
            self.estimated_rtt = (1 - ALPHA) * self.estimated_rtt + ALPHA * sample_rtt
        
        self.rto = self.estimated_rtt + 4 * self.dev_rtt
        self.rto = max(0.15, min(self.rto, 1.0))  # Min RTO 150ms
        
        # Update congestion control RTT
        self.cc.update_rtt(sample_rtt)
    
    def get_effective_window(self):
        """Get effective sending window (controlled by cwnd)"""
        return int(self.cc.get_cwnd())


def parse_ack(data):
    """Parse ACK packet: [ack_num (4B)] [SACK blocks (16B)]"""
    if len(data) < 20:
        return None, []
    
    ack_num = struct.unpack('!I', data[:4])[0]
    
    # Parse SACK blocks
    sack_blocks = []
    for i in range(2):
        offset = 4 + i * 8
        if offset + 8 <= len(data):
            block_data = data[offset:offset + 8]
            if block_data != b'\x00' * 8:
                start, end = struct.unpack('!II', block_data)
                if start != 0 or end != 0:
                    sack_blocks.append((start, end))
    
    return ack_num, sack_blocks


def send_file(sock, client_addr, file_data):
    """Send file using sliding window protocol with congestion control"""
    state = ServerState()
    file_size = len(file_data)
    all_data_sent = False
    eof_sent = False
    eof_acked = False
    
    print(f"Starting file transfer: {file_size} bytes")
    print(f"Initial cwnd: {state.cc.get_cwnd()} bytes ({state.cc.get_cwnd() / MSS:.1f} MSS)")
    print(f"Initial ssthresh: {state.cc.ssthresh / MSS:.1f} MSS")
    print(f"CUBIC_BETA: {CUBIC_BETA}, Min RTO: 150ms")
    start_time = time.time()
    
    sock.settimeout(0.01)
    
    while not eof_acked:
        current_time = time.time()
        
        # Get effective window from congestion control
        effective_window = state.get_effective_window()
        
        # Send new packets within cwnd
        while (state.next_seq_num < state.send_base + effective_window and 
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
        
        # Send EOF if all data sent
        if all_data_sent and not eof_sent and state.send_base >= file_size:
            eof_packet = Packet(file_size, EOF_MARKER)
            eof_packet.send_time = current_time
            sock.sendto(eof_packet.to_bytes(), client_addr)
            state.packets[file_size] = eof_packet
            eof_sent = True
        
        # Check for timeouts (with cascade prevention and smart handling)
        timeout_detected = False
        for seq_num, packet in list(state.packets.items()):
            if current_time - packet.send_time > state.rto:
                # Only trigger CC once per RTT window
                if not timeout_detected and not state.timeout_triggered_this_window:
                    # Check if we made recent progress (ACK within 2*RTT)
                    time_since_progress = current_time - state.last_progress_time
                    recent_progress = (state.estimated_rtt is not None and 
                                     time_since_progress < 2 * state.estimated_rtt)
                    
                    old_cwnd = state.cc.get_cwnd()
                    state.cc.on_timeout(recent_progress=recent_progress)
                    new_cwnd = state.cc.get_cwnd()
                    
                    if new_cwnd != old_cwnd:
                        progress_str = "with progress" if recent_progress else "no progress"
                        print(f"[TIMEOUT {progress_str}] cwnd: {old_cwnd/MSS:.2f} -> {new_cwnd/MSS:.2f} MSS")
                    
                    state.timeout_triggered_this_window = True
                    state.last_timeout_time = current_time
                    timeout_detected = True
                
                # Always retransmit the timed-out packet
                packet.send_time = current_time
                sock.sendto(packet.to_bytes(), client_addr)
        
        # Receive ACKs
        try:
            ack_data, _ = sock.recvfrom(MAX_PAYLOAD)
            ack_num, sack_blocks = parse_ack(ack_data)
            
            if ack_num is None:
                continue
            
            # Check if EOF ACK
            if eof_sent and ack_num > file_size:
                eof_acked = True
                break
            
            # Process ACK
            if ack_num > state.send_base:
                # New data ACKed - update RTT and cwnd
                state.last_progress_time = current_time  # Track progress
                
                if state.send_base in state.packets:
                    sample_rtt = current_time - state.packets[state.send_base].send_time
                    state.update_rtt(sample_rtt)
                
                # Calculate bytes newly ACKed
                bytes_acked = ack_num - state.send_base
                
                # Update congestion control
                old_cwnd = state.cc.get_cwnd()
                state.cc.on_ack_received(bytes_acked, current_time)
                new_cwnd = state.cc.get_cwnd()
                
                # Exit fast recovery if in it
                if state.cc.in_fast_recovery:
                    state.cc.exit_fast_recovery()
                
                # Reset timeout window flag on progress
                state.timeout_triggered_this_window = False
                
                # Log cwnd changes (for debugging)
                if int(old_cwnd / MSS) != int(new_cwnd / MSS):
                    phase = "SS" if state.cc.in_slow_start else "CA"
                    print(f"[{phase}] cwnd: {old_cwnd/MSS:.2f} -> {new_cwnd/MSS:.2f} MSS, ssthresh: {state.cc.ssthresh/MSS:.1f}")
                
                # Remove ACKed packets
                for seq in list(state.packets.keys()):
                    if seq < ack_num:
                        del state.packets[seq]
                        state.sack_retransmitted.discard(seq)
                
                # Clear hole tracking
                for hole_key in list(state.sack_hole_count.keys()):
                    if hole_key[0] < ack_num:
                        del state.sack_hole_count[hole_key]
                        del state.sack_hole_first_seen[hole_key]
                
                state.send_base = ack_num
                state.dup_ack_count.clear()
                state.last_ack_received = ack_num
                
            elif ack_num == state.send_base and ack_num == state.last_ack_received:
                # Duplicate ACK
                state.dup_ack_count[ack_num] = state.dup_ack_count.get(ack_num, 0) + 1
                
                # Fast retransmit on 3 duplicate ACKs
                if state.dup_ack_count[ack_num] == 3:
                    old_cwnd = state.cc.get_cwnd()
                    state.cc.on_fast_retransmit()
                    new_cwnd = state.cc.get_cwnd()
                    
                    print(f"[FAST_RETX] cwnd: {old_cwnd/MSS:.2f} -> {new_cwnd/MSS:.2f} MSS")
                    
                    if state.send_base in state.packets:
                        packet = state.packets[state.send_base]
                        packet.send_time = current_time
                        sock.sendto(packet.to_bytes(), client_addr)
            
            # Handle SACK blocks
            for start, end in sack_blocks:
                for seq in list(state.packets.keys()):
                    if start <= seq < end:
                        if seq in state.packets:
                            del state.packets[seq]
                            state.sack_retransmitted.discard(seq)
            
            # SACK-based proactive retransmission (sophisticated, from Part 1)
            if sack_blocks and ack_num == state.send_base:
                first_sack_start = min(block[0] for block in sack_blocks)
                
                if first_sack_start > state.send_base:
                    hole_key = (state.send_base, first_sack_start)
                    
                    # Track hole occurrences and first seen time
                    if hole_key not in state.sack_hole_count:
                        state.sack_hole_first_seen[hole_key] = current_time
                    state.sack_hole_count[hole_key] = state.sack_hole_count.get(hole_key, 0) + 1
                    
                    if state.send_base in state.packets:
                        packet = state.packets[state.send_base]
                        time_since_send = current_time - packet.send_time
                        time_since_first_seen = current_time - state.sack_hole_first_seen[hole_key]
                        packets_in_flight = len(state.packets) - (1 if file_size in state.packets else 0)
                        
                        hole_confidence = state.sack_hole_count[hole_key]
                        
                        # ULTRA AGGRESSIVE SACK thresholds
                        if state.estimated_rtt:
                            if packets_in_flight <= 1:
                                # Last packet: still conservative
                                adaptive_wait = max(0.10, state.estimated_rtt + 2 * state.dev_rtt)
                            elif hole_confidence >= 3 and time_since_first_seen > state.estimated_rtt:
                                # High confidence - very aggressive
                                adaptive_wait = max(0.05, state.estimated_rtt + state.dev_rtt)
                            else:
                                # Normal case - aggressive
                                adaptive_wait = max(0.08, state.estimated_rtt + 1.5 * state.dev_rtt)
                        else:
                            adaptive_wait = 0.1
                        
                        # Retransmit if packet pending long enough
                        # NO congestion control - SACK is just recovery
                        if (state.send_base not in state.sack_retransmitted and 
                            time_since_send > adaptive_wait):
                            packet.send_time = current_time
                            sock.sendto(packet.to_bytes(), client_addr)
                            state.sack_retransmitted.add(state.send_base)
            
            state.last_ack_received = ack_num
            
        except socket.timeout:
            continue
        except BlockingIOError:
            continue
    
    elapsed = time.time() - start_time
    throughput_mbps = (file_size * 8) / (elapsed * 1e6)
    print(f"Transfer complete: {file_size} bytes in {elapsed:.2f}s ({throughput_mbps:.2f} Mbps)")
    print(f"Final cwnd: {state.cc.get_cwnd()/MSS:.2f} MSS")


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 p2_server.py <SERVER_IP> <SERVER_PORT>")
        sys.exit(1)
    
    server_ip = sys.argv[1]
    server_port = int(sys.argv[2])
    
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
    
    # Wait for client request
    sock.settimeout(None)
    request, client_addr = sock.recvfrom(MAX_PAYLOAD)
    print(f"Received request from {client_addr}")
    
    # Send file with congestion control
    send_file(sock, client_addr, file_data)
    
    # Close
    sock.close()


if __name__ == "__main__":
    main()