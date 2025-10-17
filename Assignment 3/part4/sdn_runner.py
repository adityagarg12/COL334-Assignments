import argparse, json, time, re, os
from mininet.cli import CLI
from mininet.log import setLogLevel
from p4_topo import build, H1_IP, H2_IP
from p4_ospf import start_frr_ospf, wait_for_convergence, stop_frr, generate_meta_ospf

def if_toggle(net, e, down=True):
    a, b = net.get(e["s_i"]), net.get(e["s_j"])
    ia, ib = e["i_if"], e["j_if"]
    x = "down" if down else "up"
    a.cmd(f"ip link set {ia} {x}")
    b.cmd(f"ip link set {ib} {x}")

def iperf(h1, h2, ip2, sec, prefer3=True, tag=""):
    sl = f"h2_iperf{tag}.log" if tag else "h2_iperf.log"
    cl = f"h1_iperf{tag}.log" if tag else "h1_iperf.log"
    have3 = prefer3 and ("iperf3" in h1.cmd("which iperf3"))
    ip = ip2.split("/")[0]
    if have3:
        h2.cmd(f"iperf3 -s -1 > {sl} 2>&1 &")
        time.sleep(0.5)
        h1.cmd(f"iperf3 -c {ip} -t {int(sec)} -i 1 > {cl} 2>&1 &")
    else:
        h2.cmd(f"iperf -s > {sl} 2>&1 &")
        time.sleep(0.5)
        h1.cmd(f"iperf -c {ip} -t {int(sec)} -i 1 > {cl} 2>&1 &")
    return sl, cl

def flap(net, e, ip1, ip2, t=30, down_dur=5, down_at=2, i=1):
    h1, h2 = net.get("h1"), net.get("h2")
    tag = f"_{i}"
    sl, cl = iperf(h1, h2, ip2, t, tag=tag)
    time.sleep(down_at)
    if_toggle(net, e, True)
    time.sleep(down_dur)
    if_toggle(net, e, False)
    time.sleep(t - down_dur - down_at)
    co = h1.cmd(f"tail -n +1 {cl} || true")
    so = h2.cmd(f"tail -n +1 {sl} || true")
    return cl, sl, co, so

def to_mbps(v, u):
    m = {"K": 1/1000, "M": 1, "G": 1000}
    return float(v) * m.get(u, 1)

def parse_client_log(p):
    r = []
    if not os.path.exists(p):
        return r
    txt = open(p, "r", errors="ignore").read().splitlines()
    pat = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*sec.*?([\d\.]+)\s*([KMG])bits/sec", re.I)
    for ln in txt:
        m = pat.search(ln)
        if not m:
            continue
        s0, s1, v, u = m.groups()
        t = float(s1)
        y = to_mbps(v, u.upper())
        r.append((t, y))
    r.sort(key=lambda x: x[0])
    return r

def plot_series(series, out_path, title):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.figure()
    for lbl, pts in series:
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        plt.plot(xs, ys, marker="o", label=lbl)
    plt.xlabel("Time (s)")
    plt.ylabel("Throughput (Mbps)")
    if len(series) > 1:
        plt.legend()
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path)
    return out_path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-file", required=True)
    ap.add_argument("--converge-timeout", type=int, default=120)
    ap.add_argument("--flap-iters", type=int, default=1)
    ap.add_argument("--stabilize", type=int, default=40)
    ap.add_argument("--no-cli", action="store_true")
    ap.add_argument("--down-at", type=int, default=2)
    ap.add_argument("--down-dur", type=int, default=5)
    ap.add_argument("--iperf-sec", type=int, default=30)
    ap.add_argument("--plot-out", default="throughput.png")
    args = ap.parse_args()

    # Ensure logs directory exists
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)

    with open(args.input_file) as f:
        conf = json.load(f)

    net = build()
    meta = generate_meta_ospf(conf)

    try:
        start_frr_ospf(net, meta)
        ok = wait_for_convergence(net, meta, timeout=args.converge_timeout)
        time.sleep(max(0, args.stabilize))
        e = None
        for x in meta["edges"]:
            if x.get("fail_target") or (x["s_i"] == "s2" and x["s_j"] == "s3"):
                e = x
                break
        series = []
        for i in range(1, args.flap_iters + 1):
            cl, sl, co, so = flap(net, e, H1_IP, H2_IP, t=args.iperf_sec, down_dur=args.down_dur, down_at=args.down_at, i=i)
            print("\n==== iperf CLIENT (h1) ====\n" + co)
            print("\n==== iperf SERVER (h2) ====\n" + so)

            # Persist outputs to individual log files per iteration
            h1_out_iter = os.path.join(logs_dir, f"h1_output_iter{i}.log")
            h2_out_iter = os.path.join(logs_dir, f"h2_output_iter{i}.log")
            with open(h1_out_iter, "w") as f:
                f.write(co)
            with open(h2_out_iter, "w") as f:
                f.write(so)

            # Also keep latest copies at top level for quick inspection
            with open("h1_output.log", "w") as f:
                f.write(co)
            with open("h2_output.log", "w") as f:
                f.write(so)
            pts = parse_client_log(cl)
            series.append((f"iter{i}", pts))
        out = plot_series(series, args.plot_out, "Per-second Throughput")
        print(f"\nplot saved to {out}\n")
        if not args.no_cli:
            CLI(net)
    finally:
        stop_frr(net, meta)
        net.stop()

if __name__ == "__main__":
    setLogLevel("info")
    main()