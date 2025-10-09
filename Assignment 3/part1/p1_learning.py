from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet


class LearningSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(LearningSwitch, self).__init__(*args, **kwargs)
        # MAC address table for learning
        self.mac_to_port = {}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle switch connection and install table-miss flow entry"""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install table-miss flow entry to send unmatched packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                        ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        self.logger.info("Switch %s connected - Learning Switch", datapath.id)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        """Add a flow entry to the switch"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                  priority=priority, match=match,
                                  instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                  match=match, instructions=inst)
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle packet-in messages - Learning switch behavior"""
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore LLDP packets
        if eth.ethertype == 35020:  # LLDP ethertype
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        # Learn MAC address
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        self.logger.info("Learning Switch: packet in %s %s %s %s", dpid, src, dst, in_port)

        # Determine output port
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            self.logger.info("Learning Switch: Destination known, installing flow rule to port %s", out_port)
        else:
            out_port = ofproto.OFPP_FLOOD
            self.logger.info("Learning Switch: Destination unknown, flooding")

        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow to avoid packet_in next time for known destinations
        if out_port != ofproto.OFPP_FLOOD:
            # Create match for this specific flow
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)

            # Verify that the output port is not the same as input port
            if out_port != in_port:
                # Install flow rule on the switch
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                self.logger.info("Learning Switch: Flow rule installed - match: in_port=%s, eth_dst=%s, action: output=%s", 
                               in_port, dst, out_port)

                # Also install reverse flow if we know both directions
                if src in self.mac_to_port[dpid]:
                    reverse_match = parser.OFPMatch(in_port=out_port, eth_dst=src)
                    reverse_actions = [parser.OFPActionOutput(in_port)]
                    self.add_flow(datapath, 1, reverse_match, reverse_actions)
                    self.logger.info("Learning Switch: Reverse flow rule installed - match: in_port=%s, eth_dst=%s, action: output=%s", 
                                   out_port, src, in_port)
                return
            else:
                self.logger.info("Learning Switch: Dropping packet - output port same as input port")
                return

        # Send packet out if no flow rule was installed (flooding case)
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
