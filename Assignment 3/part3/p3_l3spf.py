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

        # Cache for installed paths to avoid re-computation
        self.installed_paths = set()
        
        # Store original link costs for restoration when links come back up
        self.original_link_costs = {}
        
        # Parse the config to build our view of the network
        self._parse_config()
        self.logger.info("Configuration loaded and parsed successfully.")
        
        # Build port-to-neighbor mapping for link failure detection
        self._build_port_neighbor_mapping()

    def _load_config(self, file_path):
        """Loads the network configuration from a JSON file."""
        with open(file_path, 'r') as f:
            return json.load(f)

    def _parse_config(self):
        """Parses the loaded config to build internal network representations."""
        self.graph = {s['name']: {} for s in self.config['switches']}
        
        # Build the graph and store original costs
        for link in self.config['links']:
            src_node = link.get('src', link.get('ssc'))
            dst_node = link['dst']
            cost = link['cost']
            
            self.graph[src_node][dst_node] = cost
            self.graph[dst_node][src_node] = cost
            
            # Store original costs for both directions
            self.original_link_costs[(src_node, dst_node)] = cost
            self.original_link_costs[(dst_node, src_node)] = cost

        for host in self.config['hosts']:
            self.host_info[host['ip']] = host
            self.ip_to_mac[host['ip']] = host['mac']
        
        for switch in self.config['switches']:
            dpid = switch['dpid']
            self.switch_info[switch['name']] = switch
            self.port_info[dpid] = {}
            interfaces = switch.get('interfaces', switch.get('interfaces', []))

            for i, iface in enumerate(interfaces, 1):
                port_no = i 
                self.ip_to_mac[iface['ip']] = iface['mac']
                self.port_info[dpid][port_no] = {'mac': iface['mac']}

        for switch in self.config['switches']:
            dpid = switch['dpid']
            interfaces = switch.get('interfaces', switch.get('interfaces', []))
            for i, iface in enumerate(interfaces, 1):
                port_no = i
                neighbor_name = iface.get('neighbor', iface.get('neighbour'))
                if neighbor_name and neighbor_name.startswith('s'):
                    neighbor_switch = self.switch_info[neighbor_name]
                    neighbor_interfaces = neighbor_switch.get('interfaces', neighbor_switch.get('interfaces', []))
                    for n_iface in neighbor_interfaces:
                        n_neighbor = n_iface.get('neighbor', n_iface.get('neighbor'))
                        if n_neighbor == switch['name']:
                            self.port_info[dpid][port_no]['neighbor_mac'] = n_iface['mac']
                            break

    def _build_port_neighbor_mapping(self):
        """Builds a mapping from (dpid, port_no) to neighbor switch name for link failure detection."""
        self.port_to_neighbor = {}
        
        for switch in self.config['switches']:
            dpid = switch['dpid']
            switch_name = switch['name']
            interfaces = switch.get('interfaces', switch.get('interfaces', []))
            
            for i, iface in enumerate(interfaces, 1):
                port_no = i
                neighbor_name = iface.get('neighbor', iface.get('neighbour'))
                
                # Only map switch-to-switch connections
                if neighbor_name and neighbor_name.startswith('s'):
                    self.port_to_neighbor[(dpid, port_no)] = neighbor_name
        
        self.logger.info(f"Built port-to-neighbor mapping with {len(self.port_to_neighbor)} entries.")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle new switch connections."""
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        self.logger.info(f"Switch dpid={datapath.id} connected.")
        self.add_flow(datapath, 0, datapath.ofproto_parser.OFPMatch(), 
                      [datapath.ofproto_parser.OFPActionOutput(datapath.ofproto.OFPP_CONTROLLER, 
                                                               datapath.ofproto.OFPCML_NO_BUFFER)])
        
    def add_flow(self, datapath, priority, match, actions):
        """Helper to add a flow entry to a switch."""
        inst = [datapath.ofproto_parser.OFPInstructionActions(datapath.ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = datapath.ofproto_parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst)
        datapath.send_msg(mod)

    def delete_flow(self, datapath, match):
        """Helper to delete a flow entry from a switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Create a flow mod message with DELETE command
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            priority=100,  # Match the priority used when installing flows
            match=match
        )
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
        if not path:
            self.logger.error(f"No path found from {src_switch} to {dst_switch}. Packet from {src_ip} to {dst_ip} will be dropped.")
            return
            
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
            src_mac = self.port_info[datapath.id][out_port]['mac']
            dst_mac = self.port_info[datapath.id][out_port].get('neighbor_mac', self.ip_to_mac[dst_ip])
            actions = [
                datapath.ofproto_parser.OFPActionDecNwTtl(),
                datapath.ofproto_parser.OFPActionSetField(eth_src=src_mac),
                datapath.ofproto_parser.OFPActionSetField(eth_dst=dst_mac),
                datapath.ofproto_parser.OFPActionOutput(out_port)
            ]
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
        interfaces = self.switch_info[f's{dpid}'].get('interfaces', self.switch_info[f's{dpid}'].get('interfaces', []))
        for i, iface in enumerate(interfaces, 1):
            if iface.get('neighbor', iface.get('neighbour')) == neighbor: return i
        return None

    def _get_port_to_host(self, dpid, host_ip):
        """Finds the port connecting to a host's subnet."""
        host_net = ip_network(self.host_info[host_ip]['connected_subnet'])
        interfaces = self.switch_info[f's{dpid}'].get('interfaces', self.switch_info[f's{dpid}'].get('interfaces', []))
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

    def _invalidate_all_installed_paths(self):
        """
        Invalidates all installed paths by deleting flow rules from switches and clearing the cache.
        This is called when the network topology changes (link up or down).
        """
        if not self.installed_paths:
            self.logger.info("No installed paths to invalidate.")
            return
        
        self.logger.info(f"Invalidating all {len(self.installed_paths)} installed paths due to topology change...")
        
        # Collect unique destination IPs from installed paths
        destination_ips = set()
        for (src_ip, dst_ip) in self.installed_paths:
            destination_ips.add(dst_ip)
        
        # Delete flow rules for each destination IP from all switches
        for dst_ip in destination_ips:
            for switch_name, switch_info in self.switch_info.items():
                dpid = switch_info['dpid']
                datapath = self.datapaths.get(dpid)
                
                if datapath:
                    # Create a match for this destination IP
                    match = datapath.ofproto_parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP, ipv4_dst=dst_ip)
                    self.delete_flow(datapath, match)
                    self.logger.info(f"Deleted flow rules for destination {dst_ip} from switch {switch_name} (dpid={dpid})")
        
        # Clear the installed paths cache completely
        self.installed_paths.clear()
        self.logger.info("All installed paths have been invalidated and cache cleared.")

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """
        Handles port status change events to detect link failures and restorations.
        When a link goes down or comes back up, the network topology is updated and all paths are invalidated.
        """
        msg = ev.msg
        reason = msg.reason
        port_desc = msg.desc
        datapath = msg.datapath
        dpid = datapath.id
        port_no = port_desc.port_no
        ofproto = datapath.ofproto
        
        # Only process MODIFY events (link state changes)
        if reason != ofproto.OFPPR_MODIFY:
            return
        
        # Check if this port is connected to another switch
        if (dpid, port_no) not in self.port_to_neighbor:
            # This port is not connected to a switch (probably a host), ignore it
            return
        
        neighbor_switch = self.port_to_neighbor[(dpid, port_no)]
        current_switch = f's{dpid}'
        
        # Determine if the link is going down or coming up
        if port_desc.state & ofproto.OFPPS_LINK_DOWN:
            # Link is going DOWN
            self.logger.info(f"===== LINK DOWN DETECTED: {current_switch} <-> {neighbor_switch} (port {port_no}) =====")
            
            # Remove the link from the graph (both directions)
            if neighbor_switch in self.graph.get(current_switch, {}):
                del self.graph[current_switch][neighbor_switch]
                self.logger.info(f"Removed edge: {current_switch} -> {neighbor_switch} from topology graph")
            
            if current_switch in self.graph.get(neighbor_switch, {}):
                del self.graph[neighbor_switch][current_switch]
                self.logger.info(f"Removed edge: {neighbor_switch} -> {current_switch} from topology graph")
            
            # Invalidate all installed paths and delete flow rules
            self._invalidate_all_installed_paths()
            
        else:
            # Link is coming UP
            self.logger.info(f"===== LINK UP DETECTED: {current_switch} <-> {neighbor_switch} (port {port_no}) =====")
            
            # Restore the link in the graph with original cost
            if (current_switch, neighbor_switch) in self.original_link_costs:
                original_cost = self.original_link_costs[(current_switch, neighbor_switch)]
                self.graph[current_switch][neighbor_switch] = original_cost
                self.graph[neighbor_switch][current_switch] = original_cost
                self.logger.info(f"Restored link: {current_switch} <-> {neighbor_switch} with cost={original_cost}")
            else:
                self.logger.warning(f"Could not find original cost for link {current_switch} <-> {neighbor_switch}")
            
            # Invalidate all installed paths to allow recomputation with new topology
            self._invalidate_all_installed_paths()