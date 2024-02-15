#!/usr/bin/env python3
# encoding: utf-8

from seedemu import *
import subprocess
import networkx as nx
import random
from ipaddress import IPv4Network


def exec(cmd):
    letters = subprocess.check_output(cmd,shell=True, text=True)
    oneLine = "".join(letters)
    return oneLine.splitlines()
    
def execNewWindow(cmd):
	subprocess.run("gnome-terminal -- bash -c \""+cmd+"\"",shell=True,check=True)



try:
	exec("sudo docker system prune -f")
except:
	pass
try:
	exec("sudo docker images -a | grep 'output' | awk '{print $3}' | sudo xargs docker rmi") #add -f to last command?
except:
	pass
	
try:
	exec("rm -rf output/")
except:
	pass



emu     = Emulator()
base    = Base()
routing = Routing()
ebgp    = Ebgp()
ibgp    = Ibgp()
ospf    = Ospf()

mode = 'notcaida' #make this a command line argument

if mode == 'caida':
	astopology = open("caida.txt","r", encoding="utf-8")
else:
	astopology = open("ASTopology.txt","r", encoding="utf-8")

astopologyLines = astopology.readlines()
astopologyLines = astopologyLines[:1000] if mode == 'caida' else astopologyLines #Remove this later when you change network to 18/14 instead of 16/16 public private subnet that it currently is
astopology.close()
	
asclients = open("ASClients.txt","r", encoding="utf-8")
if mode == 'caida':
	asclientsLines = []
else:
	asclientsLines = asclients.readlines()
asclients.close()

ASNumClients = {}
for i in range(len(asclientsLines)):
	if asclientsLines[i].startswith("#"):
		continue
	ASClient = asclientsLines[i].split(',')
	ASNumClients[ASClient[0]] = int(ASClient[1])

ASGraph = nx.Graph()
for i in range(len(astopologyLines)):
	if astopologyLines[i].startswith("#"):
		continue
	edgeData = astopologyLines[i].split(',') if mode != 'caida' else astopologyLines[i].split('\t')
	if mode == 'caida':
		ASGraph.add_edge(edgeData[0],edgeData[1],delay=random.randint(20,500),peering='cp' if int(edgeData[2]) == 1 or int(edgeData[2]) == -1 else 'p2p',customer=edgeData[0] if int(edgeData[2]) != 1 else edgeData[1],provider=edgeData[1] if int(edgeData[2]) != 1 else edgeData[0]);
	else:
		ASGraph.add_edge(edgeData[0],edgeData[1],delay=int(edgeData[2]),peering=edgeData[3],customer=edgeData[0],provider=edgeData[1]);

ASGraphNodes = list(ASGraph.nodes)
ASGraphEdges = list(ASGraph.edges)



#in order to have more than 255 ASes and IXes, need to create custom addresses
ipv4_first_octet_cntr = 10;
ipv4_second_octet_cntr = 0;

def incr_ipv4_counters():
	global ipv4_first_octet_cntr
	global ipv4_second_octet_cntr
	if ipv4_second_octet_cntr == 255:
		ipv4_second_octet_cntr = 0
		ipv4_first_octet_cntr += 1
	else:
		ipv4_second_octet_cntr += 1

class ASIP:
	def __init__(self,first_octet,second_octet):
		self.first_octet = first_octet
		self.second_octet = second_octet
		self.third_octet = 254
		self.fourth_octet = 254
	
	def nextIP(self):
		retStr = "{}.{}.{}.{}".format(self.first_octet,self.second_octet,self.third_octet,self.fourth_octet)
		if self.fourth_octet == 0:
			self.fourth_octet = 254
			self.third_octet -= 1
		else:
			self.fourth_octet -= 1
		return retStr

#These custom IPs that allow for more than 255 ASes were what was causing the destination unreacable problem! ASes were not able to communicate with each other across transit-transit edges.
#Why do the custom IPs prevent routing from working? How can they be brought back without causing the same problem? Is this an issue within SEED?
#To find everywhere that was commented to remove the custom IPs: ctrl+F "prefix" and "nextIP()"
#Also change back these IX numbers below
#Also in the seed emulator I changed seedemu/core/AddressAssignmentConstraint.py -> mapIxAddress() back to default instead of always return 100 so can only have max 255 IXes again

TransitIXes = []
TransitIXesNum = []
TransitIXCorresponding = []
TransitIXIPCorresponding = []
newIXNum = 50#100 #May want to change this later for huge networks

StubASes = []
StubASesNum = []
StubASCorresponding = []
newStubNum = 100#150000 #May want to change this later for huge networks

BetweenIXes = []
BetweenIXesNum = []
BetweenIXCorresponding = []
BetweenIXIPCorresponding = []
newBIXNum = 150#125000 #May want to change this later for huge networks

TransitASes = []
TransitASesNum = []
TransitASCorresponding = []
newTransitNum = 200#20000 #May want to change this later for huge networks

#Create transit-stub IXes
for i in range(len(ASGraphNodes)):
	if ASGraph.degree[ASGraphNodes[i]] == 1: #stub
		continue
	else: #transit
		prefix = "{}.{}.0.0/16".format(ipv4_first_octet_cntr,ipv4_second_octet_cntr) #changed /24 to /16 to increase supported number of nodes
		TransitIXes.append(base.createInternetExchange(newIXNum))#,prefix))
		TransitIXesNum.append(newIXNum)
		TransitIXCorresponding.append(ASGraphNodes[i])
		TransitIXIPCorresponding.append(ASIP(ipv4_first_octet_cntr,ipv4_second_octet_cntr))
		newIXNum += 1
		incr_ipv4_counters()

IslandIXNums = []
IslandIXCorresponding = []
IslandIXIPCorresponding = []
newIslandIXNum = 175000 #May want to change this later for huge networks

#Create Stub ASes
for i in range(len(ASGraphNodes)):
	if ASGraph.degree[ASGraphNodes[i]] == 1: #stub
		StubASes.append(base.createAutonomousSystem(newStubNum))
		StubASesNum.append(newStubNum)
		StubASCorresponding.append(ASGraphNodes[i])
		
		#Stub ASes will have a single net0 network in this network
		network = "net0"
		subnet_prefix = "{}.{}.0.0/16".format(ipv4_first_octet_cntr,ipv4_second_octet_cntr) #list(IPv4Network("{}.{}.0.0/16".format(ipv4_first_octet_cntr,ipv4_second_octet_cntr)).subnets(new_prefix = 24))[0].with_prefixlen
		subnet_ASIP = ASIP(ipv4_first_octet_cntr,ipv4_second_octet_cntr)
		#Ignore below:
		##each network can hold up to 255 hosts/connected nodes. To add another network, need a new subnet: need to change the 0 in the square brackets to a higher number
		##so currently there is a limitation that each AS can have up to 255 eth clients (probably 1 less due to the router0 also being on the network) since there is only 1 network
		StubASes[-1].createNetwork(network)#,subnet_prefix)
		
		thisStubEdge = list(ASGraph[ASGraphNodes[i]].items())[0] #0 gets the first edge, should only have one edge
		#edge has [0] which is the neighbor and [1] which is a dictionary of the properties added to the edge when it was created
		
		#adds support for islands (2 stub ASes connected to each other, basically just 2 ASes connected to each other and not connected to anything else in the network)
		try:#case when not an island
			IXNumForThisEdge = TransitIXesNum[TransitIXCorresponding.index(thisStubEdge[0])]
			IXASIP = TransitIXIPCorresponding[TransitIXCorresponding.index(thisStubEdge[0])]
		
			#Each stub will have one bgp router, this router's link to net0 will be what controls the delay between StubAS and TransitAS Edge
			asroutr = StubASes[-1].createRouter('router0').joinNetwork(
			network,
			#subnet_ASIP.nextIP()
			).joinNetwork('ix{}'.format(IXNumForThisEdge))#,IXASIP.nextIP())
		except:#case when this is an island
			try:#try to find existing islandIX under neighbor's name
				IXNumForThisEdge = IslandIXNums[IslandIXCorresponding.index(thisStubEdge[0])]
				IXASIP = IslandIXIPCorresponding[IslandIXCorresponding.index(thisStubEdge[0])]
				
				#Each stub will have one bgp router, this router's link to net0 will be what controls the delay between StubAS and TransitAS Edge
				asroutr = StubASes[-1].createRouter('router0').joinNetwork(
				network,
				#subnet_ASIP.nextIP()
				).joinNetwork('ix{}'.format(IXNumForThisEdge))#,IXASIP.nextIP())
			except:
				try:#try to find existing islandIX under this AS's name
					IXNumForThisEdge = IslandIXNums[IslandIXCorresponding.index(ASGraphNodes[i])]
					IXASIP = IslandIXIPCorresponding[IslandIXCorresponding.index(ASGraphNodes[i])]
					
					#Each stub will have one bgp router, this router's link to net0 will be what controls the delay between StubAS and TransitAS Edge
					asroutr = StubASes[-1].createRouter('router0').joinNetwork(
					network,
					#subnet_ASIP.nextIP()
					).joinNetwork('ix{}'.format(IXNumForThisEdge))#,IXASIP.nextIP())
				except:#create new islandIX and use it
					incr_ipv4_counters()
					prefix = "{}.{}.0.0/16".format(ipv4_first_octet_cntr,ipv4_second_octet_cntr) #changed /24 to /16 to increase supported number of nodes
					base.createInternetExchange(newIslandIXNum)#,prefix)
					IslandIXNums.append(newIslandIXNum)
					IslandIXCorresponding.append(ASGraphNodes[i])
					IslandIXIPCorresponding.append(ASIP(ipv4_first_octet_cntr,ipv4_second_octet_cntr))
					newIslandIXNum += 1
					
					IXNumForThisEdge = IslandIXNums[-1]
					IXASIP = IslandIXIPCorresponding[-1]
					
					#Each stub will have one bgp router, this router's link to net0 will be what controls the delay between StubAS and TransitAS Edge
					asroutr = StubASes[-1].createRouter('router0').joinNetwork(
					network,
					#subnet_ASIP.nextIP()
					).joinNetwork('ix{}'.format(IXNumForThisEdge))#,IXASIP.nextIP())
							
		
		#add delay to startup command
		delayAmt = thisStubEdge[1]['delay']
		if delayAmt>0:
			asroutr.appendStartCommand('tc qdisc del dev '+network+' root && tc qdisc add dev '+network+' root netem delay '+str(delayAmt)+'ms')
		
		#Add hosts, these hosts are blank, will add ethereum to them in the ethereum layer
		numHosts = ASNumClients.get(ASGraphNodes[i],0)
		for hostNum in range(numHosts):
			name = 'host_{}'.format(hostNum)
			host = StubASes[-1].createHost(name)
			host.joinNetwork(network)#,subnet_ASIP.nextIP())
		
		newStubNum += 1
		incr_ipv4_counters()


#Create transit-transit IXes
for i in range(len(ASGraphEdges)):
	if (ASGraphEdges[i][0] in StubASCorresponding) or (ASGraphEdges[i][1] in StubASCorresponding):
		continue
	else: #transit-transit edges only
		prefix = "{}.{}.0.0/16".format(ipv4_first_octet_cntr,ipv4_second_octet_cntr) #changed 24 to 16
		BetweenIXes.append(base.createInternetExchange(newBIXNum))#,prefix))
		BetweenIXesNum.append(newBIXNum)
		BetweenIXCorresponding.append(ASGraphEdges[i])
		BetweenIXIPCorresponding.append(ASIP(ipv4_first_octet_cntr,ipv4_second_octet_cntr))
		newBIXNum += 1
		incr_ipv4_counters()

#Create Transit ASes
for i in range(len(ASGraphNodes)):
	if ASGraph.degree[ASGraphNodes[i]] == 1: #stub
		continue
	else: #transit
		TransitASes.append(base.createAutonomousSystem(newTransitNum))
		TransitASesNum.append(newTransitNum)
		TransitASCorresponding.append(ASGraphNodes[i])
		
		#Transit ASes will have a single net1 network in this network
		network = "net1"
		subnet_prefix = "{}.{}.0.0/16".format(ipv4_first_octet_cntr,ipv4_second_octet_cntr) #list(IPv4Network("{}.{}.0.0/16".format(ipv4_first_octet_cntr,ipv4_second_octet_cntr)).subnets(new_prefix = 24))[0].with_prefixlen
		subnet_ASIP = ASIP(ipv4_first_octet_cntr,ipv4_second_octet_cntr)
		#Ignore below (updated to use ASIP with support for 255*255 number of clients/routers):
		##each network can hold up to 255 hosts/connected nodes. To add another network, need a new subnet: need to change the 0 in the square brackets to a higher number
		##so currently there is a limitation that each AS can have up to 255 eth clients (probably a lot less due to the many routers also being on the network (can only have up to 255 routers!)) since there is only 1 network
		TransitASes[-1].createNetwork(network)#,subnet_prefix)
		
		#Join this TransitAS's TransitIX
		TransitASes[-1].createRouter('tixrouter').joinNetwork(
		network,
		#subnet_ASIP.nextIP()
		).joinNetwork('ix'+str( TransitIXesNum[TransitIXCorresponding.index(ASGraphNodes[i])] ))#, TransitIXIPCorresponding[TransitIXCorresponding.index(ASGraphNodes[i])].nextIP() ) 

		#Join many BetweenIXes that are specified to link with this TransitAS
		#also add the delay for the transit-transit edges. This way of setting up the transit-transit edges with an ix in between and looping like this
		#means that we will visit each transit-transit edge twice, once from each transit AS involved in the transit-transit edge. So to easily do this
		#delay, just give half of the delay amount to both of the two routers that are connected at the transit-transit ix, one router in each transit AS
		routerCount = 0;
		for j in range(len(BetweenIXCorresponding)):
			if BetweenIXCorresponding[j][0] == ASGraphNodes[i] or BetweenIXCorresponding[j][1] == ASGraphNodes[i]:
				ttroutr = TransitASes[-1].createRouter('bixr'+str(routerCount)).joinNetwork(
				network,
				#subnet_ASIP.nextIP()
				).joinNetwork('ix'+str(BetweenIXesNum[j]))#, BetweenIXIPCorresponding[j].nextIP() )
				
				#get the transit-transit edge delay Corresponding to this betweenix
				delayAmt = ASGraph.get_edge_data(BetweenIXCorresponding[j][0],BetweenIXCorresponding[j][1])['delay']
				delayAmt = delayAmt/2.0 #remember to divide by 2
				if delayAmt>0:
					ttroutr.appendStartCommand('tc qdisc del dev '+network+' root && tc qdisc add dev '+network+' root netem delay '+str(delayAmt)+'ms')
				
				routerCount += 1
		
		#Add hosts, these hosts are blank, will add ethereum to them in the ethereum layer
		numHosts = ASNumClients.get(ASGraphNodes[i],0)
		for hostNum in range(numHosts):
			name = 'host_{}'.format(hostNum)
			host = TransitASes[-1].createHost(name)
			host.joinNetwork(network)#,subnet_ASIP.nextIP())

		newTransitNum += 1
		incr_ipv4_counters()


#BGP Peering
ASGraphEdgesWithData = list(ASGraph.edges.data())
for i in range(len(ASGraphEdgesWithData)):
	if (ASGraphEdgesWithData[i][0] in StubASCorresponding) or (ASGraphEdgesWithData[i][1] in StubASCorresponding): #stub-transit edge
		theStubAS = ASGraphEdgesWithData[i][0] if ASGraphEdgesWithData[i][0] in StubASCorresponding else ASGraphEdgesWithData[i][1]
		theTransitAS = ASGraphEdgesWithData[i][1] if ASGraphEdgesWithData[i][0] in StubASCorresponding else ASGraphEdgesWithData[i][0]
		#add island support
		try:#no island
			theIX = TransitIXesNum[TransitIXCorresponding.index(theTransitAS)]
		except:#island, check for the IX with both of the stubs like this since the way it is stored is under the name of one of the stubs at random
			try:
				theIX = IslandIXNums[IslandIXCorresponding.index(theTransitAS)]
			except:
				theIX = IslandIXNums[IslandIXCorresponding.index(theStubAS)]
		
		if ASGraphEdgesWithData[i][2]['peering'].rstrip() == 'p2p':
			#add island support
			try: #no island
				transitASNum = TransitASesNum[TransitASCorresponding.index(theTransitAS)]
			except: #island
				transitASNum = StubASesNum[StubASCorresponding.index(theTransitAS)]
			ebgp.addPrivatePeering(theIX, StubASesNum[StubASCorresponding.index(theStubAS)], transitASNum, abRelationship = PeerRelationship.Peer)
		else:
			stubASNum = StubASesNum[StubASCorresponding.index(theStubAS)]
			#add island support
			try: #no island
				transitASNum = TransitASesNum[TransitASCorresponding.index(theTransitAS)]
			except: #island
				transitASNum = StubASesNum[StubASCorresponding.index(theTransitAS)] #this transit AS is really another stub, island is stub-stub connection that is disconnected from the rest of the network
			
			customer = -1
			if ASGraphEdgesWithData[i][2]['customer'] == theStubAS:
				customer = stubASNum
			elif ASGraphEdgesWithData[i][2]['customer'] == theTransitAS:
				customer = transitASNum
			else:
				raise Exception("Illegal Graph State")
			
			provider = -1
			if ASGraphEdgesWithData[i][2]['provider'] == theStubAS:
				provider = stubASNum
			elif ASGraphEdgesWithData[i][2]['provider'] == theTransitAS:
				provider = transitASNum
			else:
				raise Exception("Illegal Graph State")
			print('cp '+str(customer)+' '+str(provider)+' '+str(theIX))
			ebgp.addPrivatePeering(theIX, provider, customer, abRelationship = PeerRelationship.Provider)
			#New method to try to fix destination unreachable problem, this wasnt it
			#try:
			#	ebgp.addRsPeers(theIX, [provider])
			#except:
			#	pass
			
	else: #transit-transit edge
		TransitAS1 = ASGraphEdgesWithData[i][0]
		TransitAS2 = ASGraphEdgesWithData[i][1]
		
		theIX = -1
		for k in range(len(BetweenIXCorresponding)):
			if (BetweenIXCorresponding[k][0] == TransitAS1 and BetweenIXCorresponding[k][1] == TransitAS2) or (BetweenIXCorresponding[k][0] == TransitAS2 and BetweenIXCorresponding[k][1] == TransitAS1):
				theIX = BetweenIXesNum[k]
				break
		
		if ASGraphEdgesWithData[i][2]['peering'].rstrip() == 'p2p':
			print('p2p '+str(TransitASesNum[TransitASCorresponding.index(TransitAS1)])+' '+str(TransitASesNum[TransitASCorresponding.index(TransitAS2)])+' '+str(theIX))
			ebgp.addPrivatePeering(theIX, TransitASesNum[TransitASCorresponding.index(TransitAS1)], TransitASesNum[TransitASCorresponding.index(TransitAS2)], abRelationship = PeerRelationship.Peer) #Change back to Peer, Done
			#New method to try to fix destination unreachable problem
			#ebgp.addRsPeers(theIX, [TransitASesNum[TransitASCorresponding.index(TransitAS1)], TransitASesNum[TransitASCorresponding.index(TransitAS2)]])
		else:
			customer = -1
			if ASGraphEdgesWithData[i][2]['customer'] == TransitAS1:
				customer = TransitASesNum[TransitASCorresponding.index(TransitAS1)]
			elif ASGraphEdgesWithData[i][2]['customer'] == TransitAS2:
				customer = TransitASesNum[TransitASCorresponding.index(TransitAS2)]
			else:
				raise Exception("Illegal Graph State")
			
			provider = -1
			if ASGraphEdgesWithData[i][2]['provider'] == TransitAS1:
				provider = TransitASesNum[TransitASCorresponding.index(TransitAS1)]
			elif ASGraphEdgesWithData[i][2]['provider'] == TransitAS2:
				provider = TransitASesNum[TransitASCorresponding.index(TransitAS2)]
			else:
				raise Exception("Illegal Graph State")
			
			ebgp.addPrivatePeering(theIX, provider, customer, abRelationship = PeerRelationship.Provider)




# Add layers to the emulator
emu.addLayer(base)
emu.addLayer(routing)
emu.addLayer(ebgp)
emu.addLayer(ibgp)
emu.addLayer(ospf)



# Create the Ethereum layer
eth = EthereumService()

# Create the Blockchain layer which is a sub-layer of Ethereum layer.
# chainName="pos": set the blockchain name as "pos"
# consensus="ConsensusMechnaism.POS" : set the consensus of the blockchain as "ConsensusMechanism.POS".
# supported consensus option: ConsensusMechanism.POA, ConsensusMechanism.POW, ConsensusMechanism.POS
blockchain = eth.createBlockchain(chainName="pos", consensus=ConsensusMechanism.POS)

# set `terminal_total_difficulty`, which is the value to designate when the Merge is happen.
blockchain.setTerminalTotalDifficulty(30)


hostAsnIds = []
for i in range(len(ASGraphNodes)):
	numHostsInAS = ASNumClients.get(ASGraphNodes[i],0)
	if numHostsInAS > 0:
		asn = -1
		if ASGraphNodes[i] in StubASCorresponding:
			asn = StubASesNum[StubASCorresponding.index(ASGraphNodes[i])]
		if ASGraphNodes[i] in TransitASCorresponding:
			asn = TransitASesNum[TransitASCorresponding.index(ASGraphNodes[i])]
		for h in range(numHostsInAS):
			hostAsnIds.append((asn,h))
	

###################################################
# Ethereum Node

i = 1
for id in range(len(hostAsnIds)):#The if statements that use the id are the reason why we need at least 5? hosts

    # Create a blockchain virtual node named "eth{}".format(i)
    e:EthereumServer = blockchain.createNode("eth{}".format(i))   
    
    # Create Docker Container Label named 'Ethereum-POS-i'
    e.appendClassName('Ethereum-POS-{}'.format(i))

    # Enable Geth to communicate with geth node via http
    e.enableGethHttp()

    # Set host in asn 150 with id 0 (ip : 10.150.0.71) as BeaconSetupNode.
    if id == 0:
    	e.setBeaconSetupNode()

    # Set host in asn 150 with id 1 (ip : 10.150.0.72) as BootNode. 
    # This node will serve as a BootNode in both execution layer (geth) and consensus layer (lighthouse).
    if id == 1:
    	e.setBootNode(True)

    # Set hosts in asn 152 and 162 with id 0 and 1 as validator node. 
    # Validator is added by deposit 32 Ethereum and is activated in realtime after the Merge.
    # isManual=True : deposit 32 Ethereum by manual. 
    #                 Other than deposit part, create validator key and running a validator node is done by codes.  
    #if id == 3:
    #    e.enablePOSValidatorAtRunning()
    #if id == 4:
    #    e.enablePOSValidatorAtRunning(is_manual=False)
    
    # Set hosts in asn 152, 153, 154, and 160 as validator node.
    # These validators are activated by default from genesis status.
    # Before the Merge, when the consensus in this blockchain is still POA, 
    # these hosts will be the signer nodes.
    if id>1:
        e.enablePOSValidatorAtGenesis()
        e.startMiner()

    # Customizing the display names (for visualiztion purpose)
    if e.isBeaconSetupNode():
        emu.getVirtualNode('eth{}'.format(i)).setDisplayName('Ethereum-BeaconSetup')
    else:
        emu.getVirtualNode('eth{}'.format(i)).setDisplayName('Ethereum-POS-{}'.format(i))
        
    #Add beacon loggging daemon
    with open("beaconCapture.py") as bcCode:
    	emu.getVirtualNode('eth{}'.format(i)).appendFile('/beaconCapture.py', bcCode.read())
    	emu.getVirtualNode('eth{}'.format(i)).appendStartCommand('python3 beaconCapture.py </dev/null &')

    # Binding the virtual node to the physical node. 
    #IMPORTANT: Changed 'eth{}'.format(i) to r'\beth{}\b'.format(i) This is because this first parameter to binding constuctor is not a regular string that will be == with the vnode name, it is actually a regex that will be
    #matched against the vnode names, so if you just put in eth1 for example, that will also match with eth10 and give it this filter which is not what was intended! We intend for this to be an exact match, only eth1 will get this
    #filter. So use this \b regex syntax for an exact word match (will match with the string 'eth1 someOtherStuff' though but not 'eth10 someOtherStuff')
    #Also the above applies to the nodeName parameter in Filter!
    emu.addBinding(Binding(r'\beth{}\b'.format(i), filter=Filter(asn=hostAsnIds[id][0], nodeName=r'\bhost_{}\b'.format(hostAsnIds[id][1]) )  ))
    print(str(Filter(asn=hostAsnIds[id][0], nodeName='host_{}'.format(hostAsnIds[id][1]) ).asn) + " " + Filter(asn=hostAsnIds[id][0], nodeName='host_{}'.format(hostAsnIds[id][1]) ).nodeName )
    print("eth"+str(i)+" should bind to as"+str(hostAsnIds[id][0])+" host_"+str(hostAsnIds[id][1]))
    i = i+1


# Add layer to the emulator
emu.addLayer(eth)

emu.render()

# Enable internetMap
# Enable etherView
docker = Docker(internetMapEnabled=True, etherViewEnabled=True)

emu.compile(docker, './output', override = True)

execNewWindow("sudo docker compose -f output/docker-compose.yml build && sudo docker compose -f output/docker-compose.yml up")
