# demo_runner.py
import json, os, time, pathlib
from topo_wordcount import make_net

K = int(os.environ.get("K", "5"))
P = int(os.environ.get("P", "0"))

# load base config and override p
cfg = json.loads(pathlib.Path("demo_config.json").read_text())
cfg["p"] = P
cfg["k"] = K
with open("demo_config.json", "w") as f:
    json.dump(cfg, f, indent=2)

net = make_net(); net.start()
h1, h2 = net.get('h1'), net.get('h2')

# start server with demo config
srv = h2.popen("./server --config demo_config.json > server_output.txt 2>&1", shell=True)
time.sleep(3)

# run client once (no --quiet): prints word frequencies + ELAPSED_MS
print(h1.cmd(f"./client --config demo_config.json"))

srv.terminate(); time.sleep(0.2); net.stop()
