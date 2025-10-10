#!/usr/bin/env python3

import json
import heapq
import random
from collections import defaultdict
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types


class L2ShortestPathForwarding(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(L2ShortestPathForwarding, self).__init__(*args, **kwargs)

        # Load configuration
        self.config = self.load_config('config.json')
        self.ecmp_enabled = self.config.get('ecmp', False)

        # Network topology representation
        self.nodes = self.config.get('nodes', [])
        self.weight_matrix = self.config.get('weight_matrix', [])
        self.graph = self.build_graph()

        # MAC to switch mapping
        self.mac_to_switch = {}

        # Datapath mappings
        self.dpid_to_node = {}
        self.node_to_dpid = {}
        self.datapaths = {}

        # Track installed flows
        self.installed_flows = set()

        self.logger.info("L2 Shortest Path Forwarding Controller Started")
        self.logger.info(f"ECMP enabled: {self.ecmp_enabled}")

    def load_config(self, config_file):
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            self.logger.info("Configuration loaded successfully")
            return config
        except:
            return {}

    def build_graph(self):
        """Build weighted graph from configuration"""
        graph = defaultdict(dict)
        for i, src_node in enumerate(self.nodes):
            for j, dst_node in enumerate(self.nodes):
                weight = self.weight_matrix[i][j]
                if weight > 0 and i != j:
                    graph[src_node][dst_node] = weight
        return graph

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle switch connection"""
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Install table-miss flow
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        # Map datapath
        dpid = datapath.id
        node_name = f's{dpid}'
        if node_name in self.nodes:
            self.dpid_to_node[dpid] = node_name
            self.node_to_dpid[node_name] = dpid
            self.datapaths[dpid] = datapath
            self.logger.info(f"Switch {node_name} (dpid={dpid}) connected")

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        """Add a flow entry"""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match,
                               instructions=inst, idle_timeout=idle_timeout, hard_timeout=hard_timeout)
        datapath.send_msg(mod)

    def dijkstra_shortest_paths(self, src, dst):
        """Compute shortest paths"""
        if src == dst:
            return [[src]], 0

        distances = {node: float('inf') for node in self.nodes}
        distances[src] = 0
        predecessors = defaultdict(list)
        visited = set()
        pq = [(0, src)]

        while pq:
            current_dist, current_node = heapq.heappop(pq)
            if current_node in visited:
                continue
            visited.add(current_node)
            if current_node == dst:
                break

            for neighbor, weight in self.graph[current_node].items():
                new_dist = current_dist + weight
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    predecessors[neighbor] = [current_node]
                    heapq.heappush(pq, (new_dist, neighbor))
                elif new_dist == distances[neighbor]:
                    if current_node not in predecessors[neighbor]:
                        predecessors[neighbor].append(current_node)

        def get_all_paths(target):
            if target == src:
                return [[src]]
            all_paths = []
            for pred in predecessors[target]:
                for path in get_all_paths(pred):
                    all_paths.append(path + [target])
            return all_paths

        paths = get_all_paths(dst) if dst in predecessors else []
        return paths, distances[dst]

    def select_path(self, paths):
        """Select path"""
        if not paths:
            return None
        if len(paths) == 1 or not self.ecmp_enabled:
            return paths[0]
        return random.choice(paths)

    def get_port_mapping(self, current_switch, next_switch):
        """Get port mapping based on actual topology link order"""
        port_map = {
            ('s1', 's2'): 2, ('s2', 's1'): 1, ('s1', 's3'): 3, ('s3', 's1'): 1,
            ('s2', 's4'): 2, ('s4', 's2'): 1, ('s3', 's5'): 2, ('s5', 's3'): 1,
            ('s4', 's6'): 2, ('s6', 's4'): 2, ('s5', 's6'): 2, ('s6', 's5'): 3,
        }
        return port_map.get((current_switch, next_switch))

    def get_host_port(self, switch_name):
        """Get host port"""
        return {'s1': 1, 's6': 1}.get(switch_name)

    def flood_to_learn_destination(self, datapath, in_port, src_mac, dst_mac, msg):
        """Flood packet to discover destination MAC location"""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        current_switch = self.dpid_to_node.get(datapath.id)

        if not current_switch:
            return

        self.logger.info(f"Flooding to learn destination {dst_mac}")

        actions = []
        host_ports = {'s1': 1, 's6': 1}

        # Flood to local host port if different from input
        if current_switch in host_ports and host_ports[current_switch] != in_port:
            actions.append(parser.OFPActionOutput(host_ports[current_switch]))

        # Send to other switches via shortest path
        for other_switch in ['s1', 's6']:
            if other_switch != current_switch:
                paths, _ = self.dijkstra_shortest_paths(current_switch, other_switch)
                if paths and len(paths[0]) > 1:
                    next_switch = paths[0][1]
                    port = self.get_port_mapping(current_switch, next_switch)
                    if port and port != in_port:
                        actions.append(parser.OFPActionOutput(port))

        if actions:
            data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                    in_port=in_port, actions=actions, data=data)
            datapath.send_msg(out)

    def install_flow_rules(self, path, actual_src_mac, actual_dst_mac):
        """Install flow rules with the EXACT MACs from packet headers"""
        flow_sig = f"{actual_src_mac}-{actual_dst_mac}"
        if flow_sig in self.installed_flows:
            return
        self.installed_flows.add(flow_sig)

        self.logger.info(f"Installing rules for path: {' -> '.join(path)}")
        self.logger.info(f"PACKET MACs - src: {actual_src_mac}, dst: {actual_dst_mac}")

        # Forward direction
        for i in range(len(path)):
            current_switch = path[i]
            dpid = self.node_to_dpid.get(current_switch)
            if dpid not in self.datapaths:
                continue

            datapath = self.datapaths[dpid]
            parser = datapath.ofproto_parser

            # Determine output port
            if i == len(path) - 1:
                out_port = self.get_host_port(current_switch)
            else:
                next_switch = path[i + 1]
                out_port = self.get_port_mapping(current_switch, next_switch)

            if out_port:
                match = parser.OFPMatch(eth_dst=actual_dst_mac)
                actions = [parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 100, match, actions)
                self.logger.info(f"Forward rule on {current_switch}: {actual_dst_mac} -> port {out_port}")

        # Reverse direction
        reverse_path = path[::-1]
        for i in range(len(reverse_path)):
            current_switch = reverse_path[i]
            dpid = self.node_to_dpid.get(current_switch)
            if dpid not in self.datapaths:
                continue

            datapath = self.datapaths[dpid]
            parser = datapath.ofproto_parser

            # Determine output port
            if i == len(reverse_path) - 1:
                out_port = self.get_host_port(current_switch)
            else:
                next_switch = reverse_path[i + 1]
                out_port = self.get_port_mapping(current_switch, next_switch)

            if out_port:
                match = parser.OFPMatch(eth_dst=actual_src_mac)
                actions = [parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, 100, match, actions)
                self.logger.info(f"Reverse rule on {current_switch}: {actual_src_mac} -> port {out_port}")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle packet-in"""
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # Get ACTUAL MACs from the packet header
        actual_dst_mac = eth.dst
        actual_src_mac = eth.src

        dpid = datapath.id
        current_switch = self.dpid_to_node.get(dpid)

        if not current_switch:
            return

        # Skip IPv6 multicast (33:33:xx:xx:xx:xx)
        if actual_dst_mac.startswith('33:33:'):
            return

        # Learn MACs from CORRECT host ports (h1=s1:1, h2=s6:1)
        host_ports = {'s1': 1, 's6': 1}
        if current_switch in host_ports and in_port == host_ports[current_switch]:
            if actual_src_mac not in self.mac_to_switch:
                self.mac_to_switch[actual_src_mac] = current_switch
                self.logger.info(f"Learned MAC {actual_src_mac} on {current_switch} port {in_port}")

        # Handle broadcast - allow ARP discovery
        if actual_dst_mac == 'ff:ff:ff:ff:ff:ff':
            actions = []
            # Flood to local host port if different from input
            if current_switch in host_ports and host_ports[current_switch] != in_port:
                actions.append(parser.OFPActionOutput(host_ports[current_switch]))

            # Send to other switch via shortest path
            for other_switch in ['s1', 's6']:
                if other_switch != current_switch:
                    paths, _ = self.dijkstra_shortest_paths(current_switch, other_switch)
                    if paths and len(paths[0]) > 1:
                        next_switch = paths[0][1]
                        port = self.get_port_mapping(current_switch, next_switch)
                        if port and port != in_port:
                            actions.append(parser.OFPActionOutput(port))

            if actions:
                data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                        in_port=in_port, actions=actions, data=data)
                datapath.send_msg(out)
            return

        # Find destination switch using ACTUAL destination MAC
        dst_switch = self.mac_to_switch.get(actual_dst_mac)
        if dst_switch is None:
            # FLOOD TO LEARN instead of dropping
            self.logger.info(f"Learning destination {actual_dst_mac} - flooding")
            self.flood_to_learn_destination(datapath, in_port, actual_src_mac, actual_dst_mac, msg)
            return

        # Same switch - direct forward
        if current_switch == dst_switch:
            out_port = host_ports.get(dst_switch)
            if out_port and out_port != in_port:
                actions = [parser.OFPActionOutput(out_port)]
                data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                        in_port=in_port, actions=actions, data=data)
                datapath.send_msg(out)
            return

        # Compute path and install rules
        paths, distance = self.dijkstra_shortest_paths(current_switch, dst_switch)
        if not paths:
            self.logger.warning(f"No path from {current_switch} to {dst_switch}")
            return

        selected_path = self.select_path(paths)
        if selected_path:
            self.logger.info(f"Path selected ({current_switch} -> {dst_switch}): "
                           f"{' -> '.join(selected_path)} (cost: {distance})")

            # Install rules using the EXACT MACs from the packet
            self.install_flow_rules(selected_path, actual_src_mac, actual_dst_mac)

            # Forward current packet
            if len(selected_path) > 1:
                next_switch = selected_path[1]
                out_port = self.get_port_mapping(current_switch, next_switch)
            else:
                out_port = self.get_host_port(current_switch)

            if out_port:
                actions = [parser.OFPActionOutput(out_port)]
                data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
                out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                        in_port=in_port, actions=actions, data=data)
                datapath.send_msg(out)
