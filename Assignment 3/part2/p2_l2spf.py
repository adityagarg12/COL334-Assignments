from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
import json
import heapq
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp, udp, lldp
from ryu.lib import hub
from ryu.base import app_manager
from ryu.controller import ofp_event




@dataclass(frozen=True)
class FlowKey:
    src_ip: str
    dst_ip: str
    proto: int
    sport: int
    dport: int


class TopologyGraph:
    def __init__(self) -> None:
        self.adjacency: Dict[int, Dict[int, int]] = {}
        self._base_costs: Dict[Tuple[int, int], int] = {}
        self.port_map: Dict[Tuple[int, int], int] = {}

    def build_from_config(self, node_names: List[str], weight_matrix: List[List[int]]) -> None:
        self.adjacency.clear()
        self._base_costs.clear()
        self.port_map.clear()

        for i, name in enumerate(node_names):
            u = int(name[1:])
            self.adjacency.setdefault(u, {})
            row = weight_matrix[i]
            for j, cost in enumerate(row):
                if i != j:
                    if cost > 0:
                        v = int(node_names[j][1:])
                        self._base_costs[(u, v)] = cost
                        self.adjacency[u][v] = cost

    def compute_all_equal_shortest_paths(self, src: int, dst: int) -> List[List[int]]:
        if src not in self.adjacency or dst not in self.adjacency:
            return []

        dist = {n: float('inf') for n in self.adjacency}
        dist[src] = 0
        prev: Dict[int, List[int]] = {n: [] for n in self.adjacency}

        heap: List[Tuple[float, int]] = [(0, src)]
        while heap:
            d_u, u = heapq.heappop(heap)
            if dist[u] < d_u:
                continue
            for v, w in self.adjacency[u].items():
                alt = w + d_u
                if alt == dist[v]:
                    prev[v].append(u)
                elif alt < dist[v]:
                    dist[v] = alt
                    prev[v] = [u]
                    heapq.heappush(heap, (alt, v))
                

        if dist[dst] == float('inf'):
            return []
        return self._rebuild_paths(prev, src, dst)

    def _rebuild_paths(self, prev: Dict[int, List[int]], src: int, dst: int) -> List[List[int]]:
        if dst == src:
            return [[src]]
        paths: List[List[int]] = []
        for p in prev[dst]:
            for partial in self._rebuild_paths(prev, src, p):
                paths.append(partial + [dst])
        return paths

    def set_link_down(self, u: int, v: int) -> None:
        u_neighbors = self.adjacency.get(u)
        if u_neighbors and v in u_neighbors:
            del u_neighbors[v]
        
        v_neighbors = self.adjacency.get(v)
        if v_neighbors and u in v_neighbors:
            del v_neighbors[u]

    def restore_link(self, u: int, v: int) -> None:
        if (u, v) in self._base_costs:
            cost = self._base_costs[(u, v)]
            self.adjacency.setdefault(u, {})[v] = cost
            self.adjacency.setdefault(v, {})[u] = cost

    def register_port_mapping(self, u: int, v: int, port_u: int, port_v: int) -> None:
        self.port_map[(u, v)] = port_u
        self.port_map[(v, u)] = port_v

    def get_port(self, from_dpid: int, to_dpid: int) -> Optional[int]:
        return self.port_map.get((from_dpid, to_dpid))


class PathPolicy:
    def __init__(self, ecmp: bool = False) -> None:
        self.ecmp = ecmp

    def choose(self, paths: List[List[int]]) -> Optional[List[int]]:
        if not paths:
            return None
        if self.ecmp and len(paths) > 1:
            return random.choice(paths)
        return paths[0]


class FlowRegistry:
    def __init__(self) -> None:
        self.active: Set[FlowKey] = set()
        self.host_location: Dict[str, int] = {}

    def learn_host(self, mac: str, dpid: int) -> bool:
        if mac not in self.host_location:
            self.host_location[mac] = dpid
            return True
        return False

    def get_host_switch(self, mac: str) -> Optional[int]:
        return self.host_location.get(mac)

    def is_active(self, fk: FlowKey) -> bool:
        return fk in self.active

    def register(self, fk: FlowKey) -> None:
        self.active.add(fk)

    def clear(self) -> None:
        self.active.clear()

    def _build_match(self, parser, src_ip: str, dst_ip: str, proto: int, sport: int, dport: int):
        if proto == 6:
            return parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=proto,
                tcp_src=sport,
                tcp_dst=dport
            )
        if proto == 17:
            return parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=proto,
                udp_src=sport,
                udp_dst=dport
            )
        return parser.OFPMatch(
            eth_type=0x0800,
            ipv4_src=src_ip,
            ipv4_dst=dst_ip,
            ip_proto=proto
        )

    def _host_port(self, dpid: int, ports_by_switch: Dict[int, List[int]], topo: TopologyGraph) -> Optional[int]:
        ports = ports_by_switch.get(dpid, [])
        inter_ports = {p for (a, b), p in topo.port_map.items() if a == dpid}
        for p in ports:
            if p not in inter_ports:
                return p
        return None

    def install_path(self, datapaths: Dict[int, object], ports_by_switch: Dict[int, List[int]],
                     topo: TopologyGraph, path: List[int],
                     src_ip: str, dst_ip: str, proto: int, sport: int, dport: int) -> None:
        for idx, sw in enumerate(path):
            dp = datapaths.get(sw)
            if not dp:
                continue

            parser = dp.ofproto_parser
            match = self._build_match(parser, src_ip, dst_ip, proto, sport, dport)

            if idx < len(path) - 1:
                next_sw = path[idx + 1]
                out_port = topo.get_port(sw, next_sw)
                if out_port is None:
                    continue
            else:
                out_port = self._host_port(sw, ports_by_switch, topo)
                if out_port is None:
                    continue

            actions = [parser.OFPActionOutput(out_port)]
            self._send_flow_mod(dp, priority=10, match=match, actions=actions)

    def _send_flow_mod(self, dp, priority: int, match, actions, buffer_id: Optional[int] = None) -> None:
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        
        if not buffer_id:
            mod = parser.OFPFlowMod(datapath=dp, 
                                   match=match,
                                   instructions=inst,
                                   priority=priority)
        else:
            mod = parser.OFPFlowMod(match=match, datapath=dp,
                                   instructions=inst,
                                   priority=priority,
                                   buffer_id=buffer_id)
        dp.send_msg(mod)

    def remove_all_ip(self, datapaths: Dict[int, object]) -> None:
        for dp in list(datapaths.values()):
            parser = dp.ofproto_parser
            match = parser.OFPMatch(eth_type=0x0800)
            self._del_flow(dp, priority=10, match=match)

    def _del_flow(self, dp, priority: int, match) -> None:
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        mod = parser.OFPFlowMod(
            datapath=dp,
            match=match,
            priority=priority,
            out_group=ofp.OFPG_ANY,
            out_port=ofp.OFPP_ANY,
            command=ofp.OFPFC_DELETE
        )
        dp.send_msg(mod)


class LLDPBeacon:
    def __init__(self) -> None:
        pass

    def start(self, datapaths: Dict[int, object], ports_by_switch: Dict[int, List[int]]) -> None:
        while True:
            for dpid, dp in list(datapaths.items()):
                if dpid in ports_by_switch:
                    for port_no in ports_by_switch[dpid]:
                        self._emit_lldp(dp, port_no)
            hub.sleep(5)

    def _emit_lldp(self, dp, port_no: int) -> None:
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(
            src='00:00:00:00:00:00',
            dst=lldp.LLDP_MAC_NEAREST_BRIDGE,
            ethertype=ether_types.ETH_TYPE_LLDP           
        ))

        chassis = lldp.ChassisID(
            chassis_id=str(dp.id).encode('utf-8'),
            subtype=lldp.ChassisID.SUB_LOCALLY_ASSIGNED
        )
        port = lldp.PortID(
            port_id=str(port_no).encode('utf-8'),
            subtype=lldp.PortID.SUB_LOCALLY_ASSIGNED
        )
        ttl = lldp.TTL(ttl=10)
        end = lldp.End()
        pkt.add_protocol(lldp.lldp((chassis, port, ttl, end)))
        pkt.serialize()

        actions = [parser.OFPActionOutput(port_no)]
        out = parser.OFPPacketOut(
            in_port=ofp.OFPP_CONTROLLER,
            actions=actions,
            data=pkt.data,
            datapath=dp,
            buffer_id=ofp.OFP_NO_BUFFER
        )
        dp.send_msg(out)

    def process(self, local_dpid: int, in_port: int, pkt: packet.Packet, topo: TopologyGraph) -> None:
        lldp_pkt = pkt.get_protocol(lldp.lldp)
        if not lldp_pkt:
            return

        chassis_id = None
        port_id = None
        for tlv in lldp_pkt.tlvs:         
            if isinstance(tlv, lldp.PortID):
                port_id = tlv.port_id.decode('utf-8')
            elif isinstance(tlv, lldp.ChassisID):
                chassis_id = tlv.chassis_id.decode('utf-8')

        if chassis_id:
            neighbor = int(chassis_id)
            if port_id:
                neigh_port = int(port_id)
                topo.register_port_mapping(local_dpid, neighbor, in_port, neigh_port)


class PacketAgent:
    def __init__(self) -> None:
        pass

    def extract_5tuple(self, pkt: packet.Packet) -> Optional[Dict]:
        eth = pkt.get_protocol(ethernet.ethernet)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if not ip_pkt:
            return None

        if ip_pkt.dst.startswith('224.') or ip_pkt.dst.startswith('255.'):
            return None

        tcp_pkt = pkt.get_protocol(tcp.tcp)
        udp_pkt = pkt.get_protocol(udp.udp)

        if tcp_pkt:
            sport = tcp_pkt.src_port
            dport = tcp_pkt.dst_port
        elif udp_pkt:
            sport = udp_pkt.src_port
            dport = udp_pkt.dst_port
        else:
            sport = 0
            dport = 0

        return {
            'src_mac': eth.src,
            'dst_mac': eth.dst,
            'src_ip': ip_pkt.src,
            'dst_ip': ip_pkt.dst,
            'proto': ip_pkt.proto,
            'sport': sport,
            'dport': dport
        }

    def flood(self, dp, in_port: int, msg) -> None:
        """
        Flood the received packet out all ports.
        Behavior preserved: if controller doesn't have the packet buffered, forward data bytes.
        """
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]

        # Use the message buffer if available, otherwise include packet data
        buffer_id = getattr(msg, "buffer_id", ofp.OFP_NO_BUFFER)
        data = msg.data if buffer_id == ofp.OFP_NO_BUFFER else None

        out = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        dp.send_msg(out)

    def forward(self, dp, in_port: int, path: List[int], msg, topo: TopologyGraph) -> None:
        """
        Forward the packet to the next hop on the provided path list.
        - Find current index of this switch in path (if missing, treat as index 0).
        - If next hop exists, fetch out port from topology and send PacketOut.
        """
        dpid = dp.id
        try:
            idx = path.index(dpid)
        except ValueError:
            idx = 0

        if idx >= len(path) - 1:
            return

        next_hop = path[idx + 1]
        out_port = topo.get_port(dpid, next_hop)
        if out_port is None:
            return

        parser = dp.ofproto_parser
        ofp = dp.ofproto

        buffer_id = getattr(msg, "buffer_id", ofp.OFP_NO_BUFFER)
        data = msg.data if buffer_id == ofp.OFP_NO_BUFFER else None

        out = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=buffer_id,
            in_port=in_port,
            actions=[parser.OFPActionOutput(out_port)],
            data=data
        )
        dp.send_msg(out)


class ReworkedL2SPF(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(ReworkedL2SPF, self).__init__(*args, **kwargs)

        self.datapaths: Dict[int, object] = {}
        self.ports_by_switch: Dict[int, List[int]] = {}

        self.topo = TopologyGraph()
        self.policy: Optional[PathPolicy] = None
        self.registry = FlowRegistry()
        self.beacon = LLDPBeacon()
        self.packet_agent = PacketAgent()

        self._load_config('config.json')
        hub.spawn(self._lldp_loop)

    def _load_config(self, path: str) -> None:
        with open(path, 'r') as f:
            cfg = json.load(f)
        ecmp = cfg.get('ecmp', False)
        self.policy = PathPolicy(ecmp)
        self.topo.build_from_config(cfg['nodes'], cfg['weight_matrix'])

    def _lldp_loop(self) -> None:
        self.beacon.start(self.datapaths, self.ports_by_switch)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev) -> None:
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        self.datapaths[dpid] = dp

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._send_default_flow(dp, priority=0, match=match, actions=actions)

        req = parser.OFPPortDescStatsRequest(dp, 0)
        dp.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_handler(self, ev) -> None:
        dp = ev.msg.datapath
        dpid = dp.id
        ports: List[int] = []
        for p in ev.msg.body:
            if p.port_no < dp.ofproto.OFPP_MAX:
                ports.append(p.port_no)
            elif p.port_no == dp.ofproto.OFPP_MAX:
                ports.append(p.port_no)
        self.ports_by_switch[dpid] = ports

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev) -> None:
        msg = ev.msg
        dp = msg.datapath
        in_port = msg.match['in_port']
        dpid = dp.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            self.beacon.process(dpid, in_port, pkt, self.topo)
            return

        info = self.packet_agent.extract_5tuple(pkt)
        if not info:
            return

        src_mac = info['src_mac']
        dst_mac = info['dst_mac']
        src_ip = info['src_ip']
        dst_ip = info['dst_ip']
        proto = info['proto']
        sport = info['sport']
        dport = info['dport']

        self.registry.learn_host(src_mac, dpid)

        fk = FlowKey(src_ip, dst_ip, proto, sport, dport)
        if self.registry.is_active(fk):
            return

        dst_sw = self.registry.get_host_switch(dst_mac)
        if dst_sw is None:
            self.registry.learn_host(src_mac, dpid)
            self.packet_agent.flood(dp, in_port, msg)
            return

        self.registry.learn_host(src_mac, dpid)
        src_sw = self.registry.get_host_switch(src_mac)
        if src_sw is None:
            return

        all_paths = self.topo.compute_all_equal_shortest_paths(src_sw, dst_sw)
        if not all_paths:
            return

        chosen = self.policy.choose(all_paths) if self.policy else all_paths[0]

        self.registry.install_path(self.datapaths, self.ports_by_switch, self.topo,
                                   chosen, src_ip, dst_ip, proto, sport, dport)
        self.registry.install_path(self.datapaths, self.ports_by_switch, self.topo,
                                   chosen[::-1], dst_ip, src_ip, proto, dport, sport)

        self.registry.register(fk)
        self.registry.register(FlowKey(dst_ip, src_ip, proto, dport, sport))

        self.packet_agent.forward(dp, in_port, chosen, msg, self.topo)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev) -> None:
        msg = ev.msg
        
        dp = msg.datapath
        dpid = dp.id
        ofp = dp.ofproto
        reason = msg.reason
        desc = msg.desc

        if reason != ofp.OFPPR_MODIFY:
            return

        port_no = desc.port_no

        neighbor: Optional[int] = None
        for (a, b), p in list(self.topo.port_map.items()):
            if a == dpid and p == port_no:
                neighbor = b
                break

        if neighbor is None:
            return

        if desc.state & ofp.OFPPS_LINK_DOWN:
            self.topo.set_link_down(dpid, neighbor)
            self._clear_flows()
        else:
            self.topo.restore_link(dpid, neighbor)
            self._clear_flows()

    def _clear_flows(self) -> None:
        if not self.registry.active:
            return
        self.registry.remove_all_ip(self.datapaths)
        self.registry.clear()

    def _send_default_flow(self, dp, priority: int, match, actions, buffer_id: Optional[int] = None) -> None:
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        
        if not buffer_id:
            mod = parser.OFPFlowMod(datapath=dp, priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=dp, buffer_id=buffer_id, priority=priority,
                                   match=match, instructions=inst)
        dp.send_msg(mod)

