from mininet.topo import Topo

class SimpleTopo(Topo):
    def build(self):
        # Add client and server
        client = self.addHost('h1')
        server = self.addHost('h2')
        # Add switch
        switch = self.addSwitch('s1')
        # Connect hosts to switch
        self.addLink(client, switch)
        self.addLink(server, switch)

topos = {'simpletopo': (lambda: SimpleTopo())}
