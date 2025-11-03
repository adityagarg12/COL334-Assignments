import socket, sys, time, struct, os

MAX_PAYLOAD = 1200
HEADER_SIZE = 20
DATA_SIZE = MAX_PAYLOAD - HEADER_SIZE
EOF_MARKER = b"EOF"
ALPHA = 0.125
BETA = 0.25

class P:
    def __init__(self, s, d):
        self.s = s
        self.d = d
        self.t0 = None
        self.t = None
        self.rtx = False
    def b(self):
        return struct.pack('!I', self.s) + b'\x00'*16 + self.d

class S:
    def __init__(self, sws):
        self.sws = sws
        self.sb = 0
        self.ns = 0
        self.pk = {}
        self.er = None
        self.dr = 0
        # OPTIMIZATION 1: More aggressive initial RTO
        self.rto = 0.2  # Reduced from 0.3
        self.max_rto = 2.0  # Reduced from 3.0
        self.min_rto = 0.1  # Reduced from 0.15
        self.bk = 1.0
        self.dc = 0
        self.last_ack = -1
        self.dups = 0
        # OPTIMIZATION 2: Track fast retransmit separately
        self.fast_rtx_seq = set()
        
    def upd_rtt(self, smp):
        if self.er is None:
            self.er = smp
            self.dr = smp/2
        else:
            self.dr = (1-BETA)*self.dr + BETA*abs(smp - self.er)
            self.er = (1-ALPHA)*self.er + ALPHA*smp
        # OPTIMIZATION 3: More responsive RTO calculation
        self.rto = max(self.min_rto, min(self.er + 3*self.dr, self.max_rto))
        self.bk = 1.0
        
    def backoff(self):
        # OPTIMIZATION 4: Less aggressive backoff
        self.bk = min(self.bk*1.5, 3.0)  # Changed from 2.0 and 4.0
        self.rto = min(self.rto*self.bk, self.max_rto)

def parse_ack(b):
    if len(b) < 20:
        return None, []
    a = struct.unpack('!I', b[:4])[0]
    s = []
    for i in range(2):
        off = 4 + i*8
        x = b[off:off+8]
        if len(x) == 8 and x != b'\x00'*8:
            st, en = struct.unpack('!II', x)
            if st or en:
                s.append((st, en))
    return a, s

def send_file(sk, ca, fd, sws):
    st = S(sws)
    n = len(fd)
    done = False
    eof_tx = False
    eof_ok = False
    # OPTIMIZATION 5: Increase socket timeout to reduce CPU spinning
    sk.settimeout(0.02)  # Increased from 0.01
    ts = time.time()
    last_send_time = 0
    
    while not eof_ok:
        now = time.time()
        
        # OPTIMIZATION 6: Send packets in bursts when window allows
        send_count = 0
        max_burst = 10  # Send up to 10 packets per burst
        while st.ns < st.sb + st.sws and not done and send_count < max_burst:
            if st.ns >= n:
                done = True
                break
            e = min(st.ns + DATA_SIZE, n)
            ch = fd[st.ns:e]
            p = P(st.ns, ch)
            p.t0 = now
            p.t = now
            sk.sendto(p.b(), ca)
            st.pk[st.ns] = p
            st.ns = e
            send_count += 1
        
        if done and not eof_tx and st.sb >= n:
            p = P(n, EOF_MARKER)
            p.t0 = now
            p.t = now
            sk.sendto(p.b(), ca)
            st.pk[n] = p
            eof_tx = True
        
        # OPTIMIZATION 7: More efficient timeout checking
        rtx_needed = []
        for s, p in st.pk.items():
            if now - p.t > st.rto:
                rtx_needed.append((s, p))
        
        for s, p in rtx_needed:
            p.t = now
            p.rtx = True
            sk.sendto(p.b(), ca)
            if s in st.fast_rtx_seq:
                st.fast_rtx_seq.remove(s)
        
        if rtx_needed:
            st.backoff()
        
        try:
            b, _ = sk.recvfrom(MAX_PAYLOAD)
            a, sack = parse_ack(b)
            if a is None:
                continue
            
            if eof_tx and a > n:
                eof_ok = True
                break
            
            if a > st.sb:
                # OPTIMIZATION 8: Update RTT only from non-retransmitted packets
                p0 = st.pk.get(st.sb)
                if p0 and not p0.rtx and p0.s not in st.fast_rtx_seq:
                    smp = now - p0.t0
                    st.upd_rtt(smp)
                
                # Clean up acknowledged packets
                for s in list(st.pk.keys()):
                    if s < a:
                        st.pk.pop(s, None)
                        st.fast_rtx_seq.discard(s)
                
                st.sb = a
                st.last_ack = a
                st.dups = 0
                
            elif a == st.sb:
                if st.last_ack == a:
                    st.dups += 1
                    # OPTIMIZATION 9: Fast retransmit on 3 duplicate ACKs
                    if st.dups == 1 and st.sb in st.pk:
                        p = st.pk[st.sb]
                        p.t = now
                        p.rtx = True
                        sk.sendto(p.b(), ca)
                        st.fast_rtx_seq.add(st.sb)
                        st.dups = 0  # Reset after fast retransmit
                else:
                    st.last_ack = a
                    st.dups = 1
            
            # OPTIMIZATION 10: More aggressive SACK-based retransmission
            if sack:
                for stt, en in sack:
                    for s in list(st.pk.keys()):
                        if stt <= s < en:
                            st.pk.pop(s, None)
                            st.fast_rtx_seq.discard(s)
                
                # If we have SACK holes, retransmit immediately
                if a == st.sb and sack and st.sb in st.pk:
                    ms = min(x[0] for x in sack)
                    if ms > st.sb:
                        p = st.pk[st.sb]
                        # More aggressive SACK-based retransmit
                        if now - p.t > max(st.min_rto, st.er * 0.8 if st.er else 0.1):
                            p.t = now
                            p.rtx = True
                            sk.sendto(p.b(), ca)
                            st.fast_rtx_seq.add(st.sb)
                            
        except socket.timeout:
            continue
        except BlockingIOError:
            continue
    
    te = time.time() - ts
    thr = n/te/1024/1024 if te > 0 else 0
    print(f"Transfer complete: {n} bytes in {te:.2f}s ({thr:.2f} MB/s)")

def main():
    D_IP = "127.0.0.1"
    D_PORT = 8080
    D_SWS = 5900
    if len(sys.argv) == 4:
        ip = sys.argv[1]
        port = int(sys.argv[2])
        sws = int(sys.argv[3])
    elif len(sys.argv) == 1:
        ip = D_IP
        port = D_PORT
        sws = D_SWS
        print(f"Using default values: IP={ip}, PORT={port}, SWS={sws}")
    else:
        print("Usage: python3 p1_server.py [<SERVER_IP> <SERVER_PORT> <SWS>]")
        sys.exit(1)
    if not os.path.exists('data.txt'):
        print("Error: data.txt not found")
        sys.exit(1)
    with open('data.txt', 'rb') as f:
        fd = f.read()
    sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sk.bind((ip, port))
    print(f"Server listening on {ip}:{port}")
    print(f"Sender window size: {sws} bytes")
    print(f"File size: {len(fd)} bytes")
    sk.settimeout(None)
    _, ca = sk.recvfrom(MAX_PAYLOAD)
    send_file(sk, ca, fd, sws)
    sk.close()
    print("Server terminated")

if __name__ == "__main__":
    main()