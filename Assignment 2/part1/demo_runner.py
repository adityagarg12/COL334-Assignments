# demo_runner.py
import json, os, time, pathlib
from topo_wordcount import make_net

K_env = os.environ.get("K")
P_env = os.environ.get("P")

# load base config
cfg = json.loads(pathlib.Path("config.json").read_text())

if P_env is not None and P_env != "":
    cfg["p"] = int(P_env)
if K_env is not None and K_env != "":
    cfg["k"] = int(K_env)

with open("config.json", "w") as f:
    json.dump(cfg, f, indent=2)

net = make_net(); net.start()
h1, h2 = net.get('h1'), net.get('h2')

# start server with demo config
srv = h2.popen("./server --config config.json > server_output.txt 2>&1", shell=True)
time.sleep(3)

# run client once (no --quiet): prints word frequencies + ELAPSED_MS
print(h1.cmd(f"./client --config config.json --quiet"))

srv.terminate(); time.sleep(0.2); net.stop()
