#!/usr/bin/env python3
# p3_unicast_l3spf.py - L3 Shortest Path Forwarding Controller (Unicast Logic)

import json
import heapq
from ipaddress import ip_address, ip_network

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, icmp
from ryu.lib.packet import ether_types

class L3UnicastController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(L3UnicastController, self).__init__(*args, **kwargs)
        self.logger.info("--- L3 Unicast Shortest Path Controller ---")
        
        # Load static configuration
        self.config = self._load_config('p3_config.json')

        # Network topology and state data structures
        self.graph = {}
        self.datapaths = {}
        self.switch_info = {}
        self.host_info = {}
        self.ip_to_mac = {}
        self.port_info = {}
        
        # Parse the config to build our view of the network
        self._parse_config()
        self.logger.info("Configuration loaded and parsed successfully.")
        
        # Cache for installed paths to avoid re-computation
        self.installed_paths = set()

    def _load_config(self, file_path):
        """Loads the network configuration from a JSON file."""
        with open(file_path, 'r') as f:
            return json.load(f)

    def _parse_config(self):
        """Parses the loaded config to build internal network representations."""
        self.graph = {s['name']: {} for s in self.config['switches']}
        for link in self.config['links']:
            src_node = link.get('src', link.get('ssc'))
            self.graph[src_node][link['dst']] = link['cost']
            self.graph[link['dst']][src_node] = link['cost']

        for host in self.config['hosts']:
            self.host_info[host['ip']] = host
            self.ip_to_mac[host['ip']] = host['mac']
        
        for switch in self.config['switches']:
            dpid = switch['dpid']
            self.switch_info[switch['name']] = switch
            self.port_info[dpid] = {}
            interfaces = switch.get('interfaces', switch.get('intesfaces', []))

            for i, iface in enumerate(interfaces, 1):
                port_no = i 
                self.ip_to_mac[iface['ip']] = iface['mac']
                self.port_info[dpid][port_no] = {'mac': iface['mac']}

        for switch in self.config['switches']:
            dpid = switch['dpid']
            interfaces = switch.get('interfaces', switch.get('intesfaces', []))
            for i, iface in enumerate(interfaces, 1):
                port_no = i
                neighbor_name = iface.get('neighbor', iface.get('neighbos'))
                if neighbor_name and neighbor_name.startswith('s'):
                    neighbor_switch = self.switch_info[neighbor_name]
                    neighbor_interfaces = neighbor_switch.get('interfaces', neighbor_switch.get('intesfaces', []))
                    for n_iface in neighbor_interfaces:
                        n_neighbor = n_iface.get('neighbor', n_iface.get('neighbos'))
                        if n_neighbor == switch['name']:
                            self.port_info[dpid][port_no]['neighbor_mac'] = n_iface['mac']
                            break


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle new switch connections."""
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        self.logger.info(f"Switch dpid={datapath.id} connected.")

        # Rule #1: Send unmatched packets to controller (lowest priority)
        self.add_flow(datapath, 0, datapath.ofproto_parser.OFPMatch(), 
                      [datapath.ofproto_parser.OFPActionOutput(datapath.ofproto.OFPP_CONTROLLER, 
                                                               datapath.ofproto.OFPCML_NO_BUFFER)])
        # Rule #2: Send ARP packets to controller (higher priority)
        self.add_flow(datapath, 10, datapath.ofproto_parser.OFPMatch(eth_type=ether_types.ETH_TYPE_ARP),
                      [datapath.ofproto_parser.OFPActionOutput(datapath.ofproto.OFPP_CONTROLLER,
                                                               datapath.ofproto.OFPCML_NO_BUFFER)])

    def add_flow(self, datapath, priority, match, actions):
        """Helper to add a flow entry to a switch."""
        inst = [datapath.ofproto_parser.OFPInstructionActions(datapath.ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = datapath.ofproto_parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    def _dijkstra(self, src_switch_name):
        """Standard Dijkstra's algorithm to compute single shortest paths."""
        distances = {node: float('inf') for node in self.graph}
        distances[src_switch_name] = 0
        previous_nodes = {node: None for node in self.graph}
        pq = [(0, src_switch_name)]
        while pq:
            dist, node = heapq.heappop(pq)
            if dist > distances[node]: continue
            for neighbor, weight in self.graph[node].items():
                new_dist = dist + weight
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    previous_nodes[neighbor] = node
                    heapq.heappush(pq, (new_dist, neighbor))
        return previous_nodes

    def _get_path(self, previous_nodes, src, dst):
        """Reconstructs the path from Dijkstra's output."""
        path = []
        curr = dst
        while curr is not None:
            path.insert(0, curr)
            curr = previous_nodes[curr]
        return path if path and path[0] == src else None

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Main handler for incoming packets."""
        pkt = packet.Packet(ev.msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP: return

        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            self._handle_arp(ev.msg.datapath, ev.msg.match['in_port'], eth, arp_pkt)
            return

        ipv4_pkt = pkt.get_protocol(ipv4.ipv4)
        if ipv4_pkt:
            self._handle_ipv4(ev.msg.datapath, ev.msg.match['in_port'], ipv4_pkt, ev.msg)
            return

    def _handle_arp(self, datapath, port, eth, arp_pkt):
        """Handles ARP requests for gateway IPs by sending a UNICAST reply."""
        if arp_pkt.opcode != arp.ARP_REQUEST: return
        
        target_mac = self.ip_to_mac.get(arp_pkt.dst_ip)
        if not target_mac: return
        
        self.logger.info(f"Sending UNICAST ARP reply for {arp_pkt.dst_ip} to {arp_pkt.src_mac}")
        
        # Craft a unicast ARP reply packet
        p = packet.Packet()
        p.add_protocol(ethernet.ethernet(ethertype=eth.ethertype, dst=arp_pkt.src_mac, src=target_mac))
        p.add_protocol(arp.arp(opcode=arp.ARP_REPLY,
                               src_mac=target_mac, src_ip=arp_pkt.dst_ip,
                               dst_mac=arp_pkt.src_mac, dst_ip=arp_pkt.src_ip))
        self._send_packet(datapath, port, p)
        
    def _handle_ipv4(self, datapath, in_port, ip_pkt, msg):
        """Handles IPv4 packets by installing UNICAST forwarding rules."""
        src_ip, dst_ip = ip_pkt.src, ip_pkt.dst
        if (src_ip, dst_ip) in self.installed_paths: return # Path already installed
            
        self.logger.info(f"New flow: {src_ip} -> {dst_ip}. Computing UNICAST path.")
        
        src_switch = self.host_info.get(src_ip, {}).get('switch')
        dst_switch = self.host_info.get(dst_ip, {}).get('switch')
        if not src_switch or not dst_switch: return
            
        previous_nodes = self._dijkstra(src_switch)
        path = self._get_path(previous_nodes, src_switch, dst_switch)
        if not path: return
            
        self.logger.info(f"Unicast path found: {' -> '.join(path)}. Installing rules.")
        
        # Install rules for both forward and reverse paths
        self._install_unicast_path(path, src_ip, dst_ip)
        
        # Cache the path to avoid re-computation
        self.installed_paths.add((src_ip, dst_ip))
        self.installed_paths.add((dst_ip, src_ip))

        # Send the initial packet along the first hop of the new unicast path
        next_hop_switch = path[1]
        out_port = self._get_port_to_neighbor(datapath.id, next_hop_switch)
        if out_port:
            actions = [datapath.ofproto_parser.OFPActionOutput(out_port)]
            out = datapath.ofproto_parser.OFPPacketOut(
                datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, 
                actions=actions, data=msg.data)
            datapath.send_msg(out)

    def _install_unicast_path(self, path, src_ip, dst_ip):
        """Installs UNICAST flow rules on each switch along the path."""
        # --- Install FORWARD path flow rules ---
        for i, node in enumerate(path):
            dp = self.datapaths[self.switch_info[node]['dpid']]
            match = dp.ofproto_parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=dst_ip)
            actions = [dp.ofproto_parser.OFPActionDecNwTtl()]
            if i < len(path) - 1: # Intermediate switch
                next_node = path[i+1]
                out_port = self._get_port_to_neighbor(dp.id, next_node)
                src_mac = self.port_info[dp.id][out_port]['mac']
                dst_mac = self.port_info[dp.id][out_port]['neighbor_mac']
                actions.extend([dp.ofproto_parser.OFPActionSetField(eth_src=src_mac),
                                dp.ofproto_parser.OFPActionSetField(eth_dst=dst_mac),
                                dp.ofproto_parser.OFPActionOutput(out_port)])
            else: # Egress switch (last hop)
                out_port = self._get_port_to_host(dp.id, dst_ip)
                src_mac = self.port_info[dp.id][out_port]['mac']
                dst_mac = self.ip_to_mac[dst_ip]
                actions.extend([dp.ofproto_parser.OFPActionSetField(eth_src=src_mac),
                                dp.ofproto_parser.OFPActionSetField(eth_dst=dst_mac),
                                dp.ofproto_parser.OFPActionOutput(out_port)])
            self.add_flow(dp, 100, match, actions)

        # --- Install REVERSE path flow rules ---
        for i, node in enumerate(reversed(path)):
            dp = self.datapaths[self.switch_info[node]['dpid']]
            match = dp.ofproto_parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=src_ip)
            actions = [dp.ofproto_parser.OFPActionDecNwTtl()]
            current_path_index = len(path) - 1 - i
            if current_path_index > 0: # Intermediate switch on reverse path
                prev_node = path[current_path_index - 1]
                out_port = self._get_port_to_neighbor(dp.id, prev_node)
                src_mac = self.port_info[dp.id][out_port]['mac']
                dst_mac = self.port_info[dp.id][out_port]['neighbor_mac']
                actions.extend([dp.ofproto_parser.OFPActionSetField(eth_src=src_mac),
                                dp.ofproto_parser.OFPActionSetField(eth_dst=dst_mac),
                                dp.ofproto_parser.OFPActionOutput(out_port)])
            else: # Egress switch on reverse path (original source)
                out_port = self._get_port_to_host(dp.id, src_ip)
                src_mac = self.port_info[dp.id][out_port]['mac']
                dst_mac = self.ip_to_mac[src_ip]
                actions.extend([dp.ofproto_parser.OFPActionSetField(eth_src=src_mac),
                                dp.ofproto_parser.OFPActionSetField(eth_dst=dst_mac),
                                dp.ofproto_parser.OFPActionOutput(out_port)])
            self.add_flow(dp, 100, match, actions)

    def _get_port_to_neighbor(self, dpid, neighbor):
        """Finds the port connecting to another switch."""
        interfaces = self.switch_info[f's{dpid}'].get('interfaces', self.switch_info[f's{dpid}'].get('intesfaces', []))
        for i, iface in enumerate(interfaces, 1):
            if iface.get('neighbor', iface.get('neighbos')) == neighbor: return i
        return None

    def _get_port_to_host(self, dpid, host_ip):
        """Finds the port connecting to a host's subnet."""
        host_net = ip_network(self.host_info[host_ip]['connected_subnet'])
        interfaces = self.switch_info[f's{dpid}'].get('interfaces', self.switch_info[f's{dpid}'].get('intesfaces', []))
        for i, iface in enumerate(interfaces, 1):
            if ip_address(iface['ip']) in host_net: return i
        return None
        
    def _send_packet(self, datapath, port, pkt):
        """Sends a packet out of a specific switch port."""
        pkt.serialize()
        actions = [datapath.ofproto_parser.OFPActionOutput(port=port)]
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=datapath.ofproto.OFP_NO_BUFFER,
            in_port=datapath.ofproto.OFPP_CONTROLLER, actions=actions, data=pkt.data)
        datapath.send_msg(out)