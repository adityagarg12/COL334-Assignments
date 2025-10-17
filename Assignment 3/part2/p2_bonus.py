
import json
import heapq
import random
import time
from collections import defaultdict
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, tcp, udp, lldp
from ryu.lib import hub


class TopologyManager:
    def __init__(self, logger):
        self.logger = logger
        self.topology = {}
        self.original_weights = {}
        self.port_links = {}
        self.port_to_neighbor = {}
        self.link_load = {}
        
    def build_from_config(self, node_list, weight_matrix):
        for i, node in enumerate(node_list):
            dpid = int(node[1:])
            self.topology[dpid] = {}
            for j, cost in enumerate(weight_matrix[i]):
                if cost > 0 and i != j:
                    neighbor_dpid = int(node_list[j][1:])
                    self.topology[dpid][neighbor_dpid] = cost
                    self.original_weights[(dpid, neighbor_dpid)] = cost
        self.logger.info("Topology nodes=%d", len(self.topology))
        for dpid, n in self.topology.items():
            self.logger.info("Neighbors s%d: %s", dpid, n)
    
    def compute_all_shortest_paths(self, src, dst):
        dist = {node: float('inf') for node in self.topology}
        dist[src] = 0
        prev = {node: [] for node in self.topology}
        pq = [(0, src)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for v, cost in self.topology[u].items():
                alt = dist[u] + cost
                if alt < dist[v]:
                    dist[v] = alt
                    prev[v] = [u]
                    heapq.heappush(pq, (alt, v))
                elif alt == dist[v]:
                    prev[v].append(u)
        if dist[dst] == float('inf'):
            self.logger.warning("No path s%d -> s%d", src, dst)
            return []
        paths = self._rebuild_all_paths(prev, src, dst)
        self.logger.info("ECMP candidates s%d->s%d cost=%s count=%d", src, dst, dist[dst], len(paths))
        for p in paths:
            self.logger.info("Path: %s", p)
        return paths
    
    def _rebuild_all_paths(self, prev, src, dst):
        if dst == src:
            return [[src]]
        a = []
        for pr in prev[dst]:
            for path in self._rebuild_all_paths(prev, src, pr):
                a.append(path + [dst])
        return a
    
    def update_link_status(self, dpid, neighbor_dpid, is_down):
        if is_down:
            if neighbor_dpid in self.topology.get(dpid, {}):
                del self.topology[dpid][neighbor_dpid]
            if dpid in self.topology.get(neighbor_dpid, {}):
                del self.topology[neighbor_dpid][dpid]
            self.logger.info("Removed link s%d<->s%d", dpid, neighbor_dpid)
        else:
            if (dpid, neighbor_dpid) in self.original_weights:
                c = self.original_weights[(dpid, neighbor_dpid)]
                self.topology[dpid][neighbor_dpid] = c
                self.topology[neighbor_dpid][dpid] = c
                self.logger.info("Restored link s%d<->s%d cost=%s", dpid, neighbor_dpid, c)
    
    def register_port_link(self, dpid, neighbor_dpid, port, neighbor_port):
        self.port_links[(dpid, neighbor_dpid)] = port
        self.port_links[(neighbor_dpid, dpid)] = neighbor_port
        self.port_to_neighbor[(dpid, port)] = neighbor_dpid
        self.port_to_neighbor[(neighbor_dpid, neighbor_port)] = dpid
        self.logger.info("Link map s%d:p%d <-> s%d:p%d", dpid, port, neighbor_dpid, neighbor_port)
    
    def get_output_port(self, src_dpid, dst_dpid):
        return self.port_links.get((src_dpid, dst_dpid))
    
    def get_link_load(self, u, v):
        return self.link_load.get((u, v), 0.0)


class PathSelector:
    def __init__(self, logger, ecmp_enabled=False, weighted=True, load_fn=None):
        self.logger = logger
        self.ecmp_enabled = ecmp_enabled
        self.weighted = weighted
        self.load_fn = load_fn or (lambda u, v: 0.0)

    def select_path(self, all_paths):
        if not all_paths:
            return None
        if self.ecmp_enabled and len(all_paths) > 1:
            if self.weighted:
                s = []
                b = []
                for p in all_paths:
                    v = 0.0
                    segs = []
                    for i in range(len(p) - 1):
                        l = self.load_fn(p[i], p[i+1])
                        v += l
                        segs.append("%d->%d:%.2f" % (p[i], p[i+1], l))
                    s.append(v)
                    b.append(" | ".join(segs))
                w = [1.0 / (1e-6 + v) for v in s]
                for i in range(len(all_paths)):
                    self.logger.info("Path idx=%d %s sum=%.2f weight=%.6f", i, b[i], s[i], w[i])
                if sum(w) > 0:
                    sel = random.choices(all_paths, weights=w, k=1)[0]
                    self.logger.info("Weighted pick %s", sel)
                    return sel
            sel = random.choice(all_paths)
            self.logger.info("Random pick %s", sel)
            return sel
        else:
            self.logger.info("Deterministic %s", all_paths[0])
            return all_paths[0]


class FlowManager:
    def __init__(self, logger):
        self.logger = logger
        self.active_flows = set()
        self.host_location = {}
    
    def learn_host(self, mac, dpid):
        if mac not in self.host_location:
            self.host_location[mac] = dpid
            self.logger.info("Learned %s at s%d", mac, dpid)
            return True
        return False
    
    def get_host_location(self, mac):
        return self.host_location.get(mac)
    
    def is_flow_active(self, flow_key):
        return flow_key in self.active_flows
    
    def register_flow(self, flow_key):
        self.active_flows.add(flow_key)
    
    def clear_all_flows(self):
        self.active_flows.clear()
        self.logger.info("Cleared all flows")
    
    def install_path_rules(self, switches, topology, switch_ports, path, 
                          src_ip, dst_ip, proto, sport, dport):
        for i in range(len(path)):
            curr = path[i]
            dp = switches.get(curr)
            if not dp:
                continue
            parser = dp.ofproto_parser
            match = self._create_match(parser, src_ip, dst_ip, proto, sport, dport)
            if i < len(path) - 1:
                nxt = path[i + 1]
                out_port = topology.get_output_port(curr, nxt)
                if not out_port:
                    self.logger.warning("No port map s%d->s%d", curr, nxt)
                    continue
            else:
                out_port = self._find_host_port(curr, switch_ports, topology)
                if not out_port:
                    self.logger.warning("No host port on s%d", curr)
                    continue
            actions = [parser.OFPActionOutput(out_port)]
            self._install_flow(dp, 10, match, actions)
            self.logger.info("Installed s%d %s:%d -> %s:%d out p%d", curr, src_ip, sport, dst_ip, dport, out_port)
    
    def _create_match(self, parser, src_ip, dst_ip, proto, sport, dport):
        if proto == 6:
            return parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip, ipv4_dst=dst_ip, ip_proto=proto, tcp_src=sport, tcp_dst=dport)
        elif proto == 17:
            return parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip, ipv4_dst=dst_ip, ip_proto=proto, udp_src=sport, udp_dst=dport)
        else:
            return parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip, ipv4_dst=dst_ip, ip_proto=proto)
    
    def _find_host_port(self, dpid, switch_ports, topology):
        ps = switch_ports.get(dpid, [])
        for p in ps:
            if p not in [pp for (d1, d2), pp in topology.port_links.items() if d1 == dpid]:
                return p
        return None
    
    def _install_flow(self, dp, priority, match, actions, buffer_id=None):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=dp, buffer_id=buffer_id, priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=dp, priority=priority, match=match, instructions=inst)
        dp.send_msg(mod)
    
    def remove_flows_from_switches(self, switches):
        for dpid, dp in switches.items():
            parser = dp.ofproto_parser
            match = parser.OFPMatch(eth_type=0x0800)
            self._remove_flow(dp, 10, match)
    
    def _remove_flow(self, dp, priority, match):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        mod = parser.OFPFlowMod(datapath=dp, command=ofp.OFPFC_DELETE, out_port=ofp.OFPP_ANY, out_group=ofp.OFPG_ANY, priority=priority, match=match)
        dp.send_msg(mod)


class LLDPManager:
    def __init__(self, logger):
        self.logger = logger
    
    def start_discovery_loop(self, switches, switch_ports):
        while True:
            for dpid, dp in list(switches.items()):
                if dpid in switch_ports:
                    for port_no in switch_ports[dpid]:
                        self.transmit_lldp(dp, port_no)
            hub.sleep(5)
    
    def transmit_lldp(self, dp, port_no):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        pkt = packet.Packet()
        pkt.add_protocol(ethernet.ethernet(ethertype=ether_types.ETH_TYPE_LLDP, src='00:00:00:00:00:00', dst=lldp.LLDP_MAC_NEAREST_BRIDGE))
        tlv_chassis_id = lldp.ChassisID(subtype=lldp.ChassisID.SUB_LOCALLY_ASSIGNED, chassis_id=str(dp.id).encode('utf-8'))
        tlv_port_id = lldp.PortID(subtype=lldp.PortID.SUB_LOCALLY_ASSIGNED, port_id=str(port_no).encode('utf-8'))
        tlv_ttl = lldp.TTL(ttl=10)
        tlv_end = lldp.End()
        tlvs = (tlv_chassis_id, tlv_port_id, tlv_ttl, tlv_end)
        pkt.add_protocol(lldp.lldp(tlvs))
        pkt.serialize()
        actions = [parser.OFPActionOutput(port_no)]
        out = parser.OFPPacketOut(datapath=dp, buffer_id=ofp.OFP_NO_BUFFER, in_port=ofp.OFPP_CONTROLLER, actions=actions, data=pkt.data)
        dp.send_msg(out)
    
    def process_lldp_packet(self, dpid, in_port, pkt, topology):
        lldp_pkt = pkt.get_protocol(lldp.lldp)
        if not lldp_pkt:
            return
        chassis_id = None
        port_id = None
        for tlv in lldp_pkt.tlvs:
            if isinstance(tlv, lldp.ChassisID):
                chassis_id = tlv.chassis_id.decode('utf-8')
            elif isinstance(tlv, lldp.PortID):
                port_id = tlv.port_id.decode('utf-8')
        if chassis_id and port_id:
            neighbor_dpid = int(chassis_id)
            neighbor_port = int(port_id)
            topology.register_port_link(dpid, neighbor_dpid, in_port, neighbor_port)


class PacketHandler:
    def __init__(self, logger):
        self.logger = logger
    
    def extract_flow_info(self, pkt):
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
        return {'src_mac': eth.src,'dst_mac': eth.dst,'src_ip': ip_pkt.src,'dst_ip': ip_pkt.dst,'proto': ip_pkt.proto,'sport': sport,'dport': dport}
    
    def flood_packet(self, dp, in_port, msg):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]
        data = None
        if msg.buffer_id == ofp.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
        dp.send_msg(out)
    
    def forward_packet(self, dp, in_port, path, msg, topology):
        dpid = dp.id
        try:
            idx = path.index(dpid)
        except ValueError:
            idx = 0
        if idx < len(path) - 1:
            nxt = path[idx + 1]
            out_port = topology.get_output_port(dpid, nxt)
            if not out_port:
                self.logger.warning("No port map s%d->s%d forward", dpid, nxt)
                return
            parser = dp.ofproto_parser
            actions = [parser.OFPActionOutput(out_port)]
            data = None
            if msg.buffer_id == dp.ofproto.OFP_NO_BUFFER:
                data = msg.data
            out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
            dp.send_msg(out)


class L2ShortestPathForwarding(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(L2ShortestPathForwarding, self).__init__(*args, **kwargs)
        self.switches = {}
        self.switch_ports = {}
        self.topology = TopologyManager(self.logger)
        self.path_selector = None
        self.flow_manager = FlowManager(self.logger)
        self.lldp_manager = LLDPManager(self.logger)
        self.packet_handler = PacketHandler(self.logger)
        self.port_prev = {}
        self.last_link_log = {}
        self._load_configuration('config.json')
        self.lldp_thread = hub.spawn(self._lldp_discovery_loop)
        self.stats_thread = hub.spawn(self._port_stats_poll_loop)
        self.logger.info("Controller started")
    
    def _load_configuration(self, path):
        self.logger.info("Loading %s", path)
        with open(path, 'r') as f:
            cfg = json.load(f)
        ecmp_enabled = cfg['ecmp']
        self.path_selector = PathSelector(self.logger, ecmp_enabled, True, self.topology.get_link_load)
        self.logger.info("ECMP=%s WeightedECMP=%s", ecmp_enabled, True)
        self.topology.build_from_config(cfg['nodes'], cfg['weight_matrix'])
    
    def _port_stats_poll_loop(self):
        while True:
            for dpid, dp in list(self.switches.items()):
                req = dp.ofproto_parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY)
                dp.send_msg(req)
            hub.sleep(1)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def handle_port_stats_reply(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        now = time.time()
        ofp = dp.ofproto
        for s in ev.msg.body:
            if s.port_no > ofp.OFPP_MAX:
                continue
            k = (dpid, s.port_no)
            tot = int(s.rx_bytes) + int(s.tx_bytes)
            if k in self.port_prev:
                pt, pv = self.port_prev[k]
                dt = now - pt
                if dt > 0:
                    d = tot - pv
                    if d < 0:
                        d = 0
                    r = (d * 8.0) / dt
                    nbr = self.topology.port_to_neighbor.get(k)
                    if nbr:
                        self.topology.link_load[(dpid, nbr)] = r
                        lk = (dpid, nbr)
                        lt = self.last_link_log.get(lk, 0)
                        if now - lt >= 5:
                            self.logger.info("Load s%d->s%d p%d %.2fbps", dpid, nbr, s.port_no, r)
                            self.last_link_log[lk] = now
            self.port_prev[k] = (now, tot)

    def _lldp_discovery_loop(self):
        self.lldp_manager.start_discovery_loop(self.switches, self.switch_ports)
    
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def handle_switch_features(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        dpid = dp.id
        self.switches[dpid] = dp
        self.logger.info("Switch s%d connected", dpid)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._install_flow(dp, 0, match, actions)
        req = parser.OFPPortDescStatsRequest(dp, 0)
        dp.send_msg(req)
    
    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def handle_port_desc_stats(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        ps = []
        for port in ev.msg.body:
            if port.port_no <= dp.ofproto.OFPP_MAX:
                ps.append(port.port_no)
        self.switch_ports[dpid] = ps
        self.logger.info("Ports s%d: %s", dpid, ps)
    
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def handle_packet_in(self, ev):
        msg = ev.msg
        dp = msg.datapath
        in_port = msg.match['in_port']
        dpid = dp.id
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            self.lldp_manager.process_lldp_packet(dpid, in_port, pkt, self.topology)
            return
        f = self.packet_handler.extract_flow_info(pkt)
        if not f:
            return
        src_mac = f['src_mac']
        dst_mac = f['dst_mac']
        src_ip = f['src_ip']
        dst_ip = f['dst_ip']
        proto = f['proto']
        sport = f['sport']
        dport = f['dport']
        self.flow_manager.learn_host(src_mac, dpid)
        flow_key = (src_ip, dst_ip, proto, sport, dport)
        if self.flow_manager.is_flow_active(flow_key):
            return
        dst_switch = self.flow_manager.get_host_location(dst_mac)
        if not dst_switch:
            self.flow_manager.learn_host(src_mac, dpid)
            self.packet_handler.flood_packet(dp, in_port, msg)
            return
        self.flow_manager.learn_host(src_mac, dpid)
        self.logger.info("New flow %s:%d -> %s:%d proto=%d", src_ip, sport, dst_ip, dport, proto)
        src_switch = self.flow_manager.get_host_location(src_mac)
        all_paths = self.topology.compute_all_shortest_paths(src_switch, dst_switch)
        if not all_paths:
            self.logger.error("No path s%d -> s%d", src_switch, dst_switch)
            return
        selected_path = self.path_selector.select_path(all_paths)
        self.logger.info("Install path %s for %s -> %s", selected_path, src_ip, dst_ip)
        self.flow_manager.install_path_rules(self.switches, self.topology, self.switch_ports, selected_path, src_ip, dst_ip, proto, sport, dport)
        self.flow_manager.install_path_rules(self.switches, self.topology, self.switch_ports, selected_path[::-1], dst_ip, src_ip, proto, dport, sport)
        self.flow_manager.register_flow(flow_key)
        self.flow_manager.register_flow((dst_ip, src_ip, proto, dport, sport))
        self.packet_handler.forward_packet(dp, in_port, selected_path, msg, self.topology)
    
    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def handle_port_status(self, ev):
        msg = ev.msg
        reason = msg.reason
        port = msg.desc
        dp = msg.datapath
        dpid = dp.id
        ofp = dp.ofproto
        if reason != ofp.OFPPR_MODIFY:
            return
        port_no = port.port_no
        neighbor_dpid = None
        for (d1, d2), p in list(self.topology.port_links.items()):
            if d1 == dpid and p == port_no:
                neighbor_dpid = d2
                break
        if not neighbor_dpid:
            return
        if port.state & ofp.OFPPS_LINK_DOWN:
            self.logger.info("Link DOWN s%d<->s%d", dpid, neighbor_dpid)
            self.topology.update_link_status(dpid, neighbor_dpid, is_down=True)
            self._clear_all_flows()
        else:
            self.logger.info("Link UP s%d<->s%d", dpid, neighbor_dpid)
            self.topology.update_link_status(dpid, neighbor_dpid, is_down=False)
            self._clear_all_flows()
    
    def _clear_all_flows(self):
        if not self.flow_manager.active_flows:
            return
        self.logger.info("Clearing flows")
        self.flow_manager.remove_flows_from_switches(self.switches)
        self.flow_manager.clear_all_flows()
    
    def _install_flow(self, dp, priority, match, actions, buffer_id=None):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=dp, buffer_id=buffer_id, priority=priority, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=dp, priority=priority, match=match, instructions=inst)
        dp.send_msg(mod)
