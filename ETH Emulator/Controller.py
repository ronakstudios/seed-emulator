import subprocess
from strip_ansi import strip_ansi
import matplotlib.pyplot as plt
from datetime import datetime
from datetime import timezone
import networkx as nx
import time
import json
from dsplot.graph import Graph
import copy
from pyvis.network import Network
import fileinput
import math
import random
import traceback

def exec(cmd):
    letters = subprocess.check_output(cmd,shell=True, text=True)
    oneLine = "".join(letters)
    return oneLine.splitlines()

def execOnDockerHost(hostName,cmd):
    return exec("sudo docker exec -it -t "+hostName+" /bin/bash -c '"+cmd+"'")

def getHostNames():
    hostNamesUnmodified = exec("sudo docker ps --format \"{{.ID}} {{.Names}}\" | grep Ethereum-POS")
    hostNames = [hostName[:hostName.find(" ")] if " " in hostName else hostName for hostName in hostNamesUnmodified]
    return hostNames
    
def getDelayRouters():
	hostNamesUnmodified = exec("sudo docker ps --format \"{{.ID}} {{.Names}}\" | grep router0")
	net0hostNames = [hostName[:hostName.find(" ")] if " " in hostName else hostName for hostName in hostNamesUnmodified]
	try:
		hostNamesUnmodified2 = exec("sudo docker ps --format \"{{.ID}} {{.Names}}\" | grep bixr")
	except:
		hostNamesUnmodified2 = []
	net1hostNames = [hostName[:hostName.find(" ")] if " " in hostName else hostName for hostName in hostNamesUnmodified2]
	return (net0hostNames, net1hostNames)

def execGethOnDockerHost(hostName,cmd):
    return execOnDockerHost(hostName,"geth attach <<< \""+cmd+"\""); #should really use the --exec option in geth attach instead

def tipBlockNumber(hostName):
    return int(strip_ansi(execGethOnDockerHost(hostName,"eth.blockNumber")[-2]));

def getBlockTimes(hostName,numBlocksBack):
    currentTip = tipBlockNumber(hostName);
    blocksBack = currentTip - numBlocksBack;
    previousBlockTime = int(strip_ansi(execGethOnDockerHost(hostName,"eth.getBlock("+str(blocksBack)+").timestamp")[-2]));
    blockTimes = []
    print("Getting block times...")
    for i in range(blocksBack+1,currentTip+1):
        currentBlockTime = int(strip_ansi(execGethOnDockerHost(hostName,"eth.getBlock("+str(i)+").timestamp")[-2]));
        blockTimes.append(currentBlockTime - previousBlockTime);
        previousBlockTime = currentBlockTime;
        print(str(100*(i-blocksBack-1)/numBlocksBack)+"%",end="\r");
    return (range(blocksBack+1,currentTip+1),blockTimes);

def getIP(hostName):#assumes net0 (the local network you specify in SEED when setting up network topology)
	try:
		return execOnDockerHost(hostName,"ip -o -4 addr show dev net0 | grep -oP \"inet \\K[\\d.]+\"")
	except:
		return execOnDockerHost(hostName,"ip -o -4 addr show dev net1 | grep -oP \"inet \\K[\\d.]+\"")
    
def getIPNet(hostName,network):
    return execOnDockerHost(hostName,"ip -o -4 addr show dev "+network+" | grep -oP \"inet \\K[\\d.]+\"") 

def getETHAddr(hostName):
    return strip_ansi(execGethOnDockerHost(hostName,"eth.coinbase")[-2]);

def getBlockProposerAddr(hostName, blockNum):#gets proposer based on block head, have to trust that proposer was honest in putting thier own name in block
    return strip_ansi(execGethOnDockerHost(hostName,"eth.getBlock("+str(blockNum)+").miner")[-2])

def getHostAddrs(hostNames):
    hostAddrs = {}
    for hostName in hostNames:
        hostAddrs[getETHAddr(hostName)] = hostName
    return hostAddrs

def getBlockProposer(hostName,hostAddrs,blockNum):
    return hostAddrs[getBlockProposerAddr(hostName,blockNum)]

def getBlockRecievedTime(hostName,blockNum):
    timestamp = execOnDockerHost(hostName,"cat gethLog.log | grep INFO | grep \"Imported new potential chain segment\" | grep \"number="+str(blockNum)+"\" | grep -oP \"\\[\\K\\d+-\\d+\\|\\d+:\\d+:\\d+\\.\\d+\"")
    timestamp = "2023-" + timestamp[0] #change this to get the year programatically (shouldnt even matter since we only look at the difference between timestamps across a few seconds)
    dateTime = datetime.strptime(timestamp, "%Y-%m-%d|%H:%M:%S.%f")
    unixTime = int(dateTime.timestamp())
    #fix that the delay is too short by making it a float with the milliseconds
    return unixTime + (int(timestamp[-3:])/1000.0)

def getBlockRecievedTimeDiffs(hostName): #old, this gives the interblock times for a node
    timestamps = execOnDockerHost(hostName,"cat gethLog.log | grep INFO | grep \"Imported new potential chain segment\" | grep -oP \"\\[\\K\\d+-\\d+\\|\\d+:\\d+:\\d+\\.\\d+\"")
    timeDiffs = []
    prevTime = 0
    for i in range(len(timestamps)):
        thisTime = int(datetime.strptime("2023-"+timestamps[i],"%Y-%m-%d|%H:%M:%S.%f").timestamp()) + (int(timestamps[i][-3:])/1000.0)
        if i==0:
            prevTime = thisTime
        else:
            timeDiffs.append(thisTime-prevTime)
            prevTime = thisTime
    return timeDiffs
    
def getBlockPropogationTimes(hostNames,printLongTimes,removeLongTimes): #Finds proposer by seeing who has the min time, not based on block header data
    timestampsOnAllMachines = []
    correspondingBlkNumbers = []
    #minNumBlocks = 0;
    maxBlkNum = 0;
    minBlkNum = -1;
    for i in range(len(hostNames)):
    	blkRecievedTimestamps = execOnDockerHost(hostNames[i],"cat gethLog.log | grep INFO | grep \"Imported new potential chain segment\" | grep -oP \"\\[\\K\\d+-\\d+\\|\\d+:\\d+:\\d+\\.\\d+\"")
    	coresspondingBlkNums = execOnDockerHost(hostNames[i],"cat gethLog.log | grep INFO | grep \"Imported new potential chain segment\" | grep -oP \"number=\\K\\d+\"")
    	
    	blkRecievedTimes = [int(datetime.strptime("2023-"+t,"%Y-%m-%d|%H:%M:%S.%f").timestamp()) + (int(t[-3:])/1000.0) for t in blkRecievedTimestamps]
    	coresspondingBlkNums = [int(n) for n in coresspondingBlkNums]
    	coresspondingBlkNums = coresspondingBlkNums[:len(blkRecievedTimes)]
    	
    	timestampsOnAllMachines.append(blkRecievedTimes)
    	correspondingBlkNumbers.append(coresspondingBlkNums)
    	maxBlkNum = coresspondingBlkNums[-1] if coresspondingBlkNums[-1] > maxBlkNum else maxBlkNum
    	minBlkNum = coresspondingBlkNums[0] if minBlkNum == -1 or coresspondingBlkNums[-1] < minBlkNum else minBlkNum
    	#minNumBlocks = len(blkRecievedTimestamps) if (minNumBlocks == 0 or minNumBlocks > len(blkRecievedTimestamps)) else minNumBlocks
    
    blockPropogationDelays1D = []
    for blkNum in range(minBlkNum,maxBlkNum+1):
    	minBlockTime = -1.0 #This is the proposer's time
    	minBlockTimeHost = 0;
    	for i in range(len(hostNames)): #i is host number
    		try:
    			blkIndex = correspondingBlkNumbers[i].index(blkNum)
    			blkTimestamp = timestampsOnAllMachines[i][blkIndex]
    			
    			minBlockTimeHost = i if minBlockTime == -1.0 or minBlockTime > blkTimestamp else minBlockTimeHost
    			minBlockTime = blkTimestamp if minBlockTime == -1.0 or minBlockTime > blkTimestamp else minBlockTime
    		except:
    			pass
    	for i in range(len(hostNames)):
    		if i != minBlockTimeHost: #use this to remove the zero propogation time value at each block from the host that is the proposer
    			try:
    				blkIndex = correspondingBlkNumbers[i].index(blkNum)
    				blkTimestamp = timestampsOnAllMachines[i][blkIndex]
    				if not removeLongTimes or ((blkTimestamp - minBlockTime) < 1):
    					blockPropogationDelays1D.append(blkTimestamp - minBlockTime)
    				if printLongTimes and ((blkTimestamp - minBlockTime) > 3):
    					print("Block: "+str(blkNum)+" Host: "+hostNames[i]+" Time: "+str(blkTimestamp - minBlockTime))
    			except:
    				pass
    return blockPropogationDelays1D

def addDelay(hostName,delayAmt):#amt in ms #assumes net0 (the local network you specify in SEED when setting up network topology)
    execOnDockerHost(hostName,"tc qdisc del dev net0 root")
    execOnDockerHost(hostName,"tc qdisc add dev net0 root netem delay "+str(delayAmt)+"ms")
    
def addDelayNet(hostName,delayAmt,network):
    execOnDockerHost(hostName,"tc qdisc del dev "+network+" root")
    execOnDockerHost(hostName,"tc qdisc add dev "+network+" root netem delay "+str(delayAmt)+"ms")

#Issue, transit-transit connections appear twice because their delay is halved and spread across two bixr routers!
#to fix this, in network creation, maybe also add the betweenIX number that the bixr routers are associated with since each transit-transit connection has its own betweenIX and you will be able to group the two bixr routers
#this way and then outwardly show them as 1 element of the delayVec, internally halving the delay across the two routers or just putting the delay on one of the routers
delayRoutersNet0 = [] #hostnames
delayRoutersNet1 = [] #hostnames
def delayVector(delayVec):
	global delayRoutersNet0
	global delayRoutersNet1
	delVLen = delayVectorLen()
	if len(delayVec) != delVLen:
		print("Input array must be length "+str(delVLen))
		return
	for i in range(len(delayRoutersNet0)):
		addDelayNet(delayRoutersNet0[i],delayVec[i],"net0")
	for j in range(len(delayRoutersNet1)):
		addDelayNet(delayRoutersNet1[j],delayVec[i+j],"net1")

def delayVectorLen():
	global delayRoutersNet0
	global delayRoutersNet1
	if delayRoutersNet0 == [] and delayRoutersNet1 == []:
		(delayRoutersNet0,delayRoutersNet1) = getDelayRouters()
	return len(delayRoutersNet0)+len(delayRoutersNet1)

def disconnectConnect(hostName,disconnect):
	if disconnect:
		execOnDockerHost(hostName,"echo \"1;net_down\" | bash seedemu_worker")
	else:
		execOnDockerHost(hostName,"echo \"1;net_up\" | bash seedemu_worker")
	
def disconnectVector(delayVec): #In the list disconnectVec, if an entry is True it will be disconnected, if False it will be reconnected
	global delayRoutersNet0
	global delayRoutersNet1
	delVLen = delayVectorLen()
	if len(delayVec) != delVLen:
		print("Input array must be length "+str(delVLen))
		return
	for i in range(len(delayRoutersNet0)):
		disconnectConnect(delayRoutersNet0[i],delayVec[i])
	for j in range(len(delayRoutersNet1)):
		disconnectConnect(delayRoutersNet1[j],delayVec[i+j])

def blockProposerByTimeGeth(hostNames,hostAddrs,blockNum):
    minTime = 0.0;
    minTimeHostName = "";
    for i in range((len(hostNames))):
        try:
            aHostBlkRecievedTime = getBlockRecievedTime(hostNames[i],blockNum)
            if minTime == 0.0 or minTime>aHostBlkRecievedTime:
                minTime = aHostBlkRecievedTime
                minTimeHoseName = hostNames[i]
        except:
            pass
    return (minTimeHostName,minTime)
    
def gethPeers(hostName):
    numPeers = int(strip_ansi(execGethOnDockerHost(hostName,"admin.peers.length")[-2]))
    peerIPs = []
    for i in range(numPeers):
    	peerIP = strip_ansi(execGethOnDockerHost(hostName,"admin.peers["+str(i)+"].network.remoteAddress")[-2]).replace('"','') #this last part removes quotes
    	peerIP = peerIP[:-6] #remove the port number
    	peerIPs.append(peerIP)
    return peerIPs

def beaconPeers(hostName):
	nodeIP = getIP(hostName)[0]
	peerIPs = execOnDockerHost(hostName,"curl -X GET \"http://"+nodeIP+":8000/eth/v1/node/peers\" -H  \"accept: application/json\" -sS | jq \".[\\\"data\\\"] | map(select(.state == \\\"connected\\\")) | map(.last_seen_p2p_address)\" | tr -d \"[ ]\"");
	#Notice how this needs to be modified from the original command to remove all single quotes with execOnDockerHost, will not work otherwise. In places where you use single quotes because the input string has double quotes, need to escape the escape of the double quotes, so you are changing the input to jq from ' "" ' to " \"\" " so that it is compatible with execOnDockerHost (no single quotes), and then to put that in a python string you escape it again: \" \\\"\\\" \" 
	#curl -X GET "http://hostIP:8000/eth/v1/node/peers" -H  "accept: application/json" -sS | jq '.["data"] | map(select(.state == "connected")) | map(.last_seen_p2p_address)' | tr -d '[ ]'
	#Output looks like this:
	#	
	#"/ip4/10.161.0.73/tcp/57812",
	#"/ip4/10.164.0.72/tcp/49066",
	#"/ip4/10.153.0.71/tcp/48216",
	#"/ip4/10.163.0.73/tcp/38668",
	#"/ip4/10.163.0.71/tcp/36870",
	#"/ip4/10.162.0.72/tcp/60444",
	#"/ip4/10.152.0.73/tcp/44622"
	#
	peerIPs=peerIPs[1:-1] #remove the first and last empty lines
	for i in range(len(peerIPs)):
		peerIPs[i] = peerIPs[i].replace(',','').replace('"','').split('/')[2]
	return peerIPs
		
	
def constructPeerGraph(hostNames,getPeersFunction): #getPeersFunction is either gethPeers or beaconPeers
	G = nx.MultiGraph()
	for hostName in hostNames:
		nodeIP = getIP(hostName)[0]
		peerIPs = getPeersFunction(hostName)
		for peerIP in peerIPs:
			G.add_edge(nodeIP,peerIP)
	return G
	
def plotPeerGraph(hostNames,getPeersFunction,title,spring):
	G = constructPeerGraph(hostNames,getPeersFunction)
	fig, ax = plt.subplots()
	pos = nx.spring_layout(G, iterations=50, seed=227,k = 5/math.sqrt(len(hostNames))) if spring else nx.shell_layout(G)
	nx.draw(G, pos, node_size=0, edge_color="r", with_labels=True)
	ax.set_title(title)
	plt.show(block = False)	

def stripAllANSI(strarray):
	retarr = []
	for s in strarray:
		retarr.append(strip_ansi(s))
	return retarr

def combine(strarray):
	ret = ""
	for s in strarray:
		ret = ret + s
	return ret
	
def popcount16str(instr):
	return bin(int(instr,16)).count('1')
	
def listSplit(execArr,sep):
	ret = []
	s = 0
	for i in range(len(execArr)):
		if strip_ansi(execArr[i]) == sep:
			ret.append(execArr[s:i])
			s = i+1
	return ret
		

def oldPlotBeaconBlocks(hostNames):
	#curl -X GET "http://10.2.254.247:8000/eth/v1/beacon/blocks/21/root" -H  "accept: application/json" -sS | jq '.data.root'
	#curl -X GET "http://10.2.254.247:8000/eth/v1/beacon/blocks/21" -H  "accept: application/json" -sS | jq '.data.message.parent_root'
	#curl -X GET "http://10.2.254.247:8000/eth/v1/beacon/blocks/21/attestations" -H  "accept: application/json" -sS | jq '.data[] | {aggregation_bits, "beacon_block_root": .data.beacon_block_root}'
	blkParent = {} #actually block children now
	blkAttestCount = {}
	genesis = strip_ansi(execOnDockerHost(hostNames[0],"curl -X GET \"http://"+getIP(hostNames[0])[0]+":8000/eth/v1/beacon/blocks/0/root\" -H  \"accept: application/json\" -sS | jq \".data.root\"")[0]);
	
	tail = tipBlockNumber(hostNames[0]) #THIS IS NOT THE METHOD TO USE FOR BEACON BLOCKS! THIS IS EXECUTION CHAIN TIP BLOCK NUMBER
	head = max(tail - 15,0);
	
	
	for hostName in hostNames:
		nodeIP = getIP(hostName)[0]
		allBlocks = listSplit(execOnDockerHost(hostName,"for i in {"+str(head)+".."+str(tail)+"}; do curl -X GET \"http://"+nodeIP+":8000/eth/v1/beacon/blocks/$i/root\" -H  \"accept: application/json\" -sS | jq \".data.root\"; echo \"SEPERATOR\"; done"),"SEPERATOR");
		allBlockParents = listSplit(execOnDockerHost(hostName,"for i in {"+str(head)+".."+str(tail)+"}; do curl -X GET \"http://"+nodeIP+":8000/eth/v1/beacon/blocks/$i\" -H  \"accept: application/json\" -sS | jq \".data.message.parent_root\"; echo \"SEPERATOR\"; done"),"SEPERATOR");
		allAttestations = listSplit(execOnDockerHost(hostName,"for i in {"+str(head)+".."+str(tail)+"}; do curl -X GET \"http://"+nodeIP+":8000/eth/v1/beacon/blocks/$i/attestations\" -H  \"accept: application/json\" -sS | jq \".data[] | {aggregation_bits, \\\"beacon_block_root\\\": .data.beacon_block_root}\"; echo \"SEPERATOR\"; done"),"SEPERATOR");
		for i in range(len(allBlocks)-1):
			aBlock = strip_ansi(allBlocks[i][0]).replace('"','');
			aBlockParent = strip_ansi(allBlockParents[i][0]).replace('"','');
			try:
				attestations = "["+combine(stripAllANSI(allAttestations[i]))+"]";
				numBlkHashPairs = [(popcount16str(obj["aggregation_bits"]), obj["beacon_block_root"]) for obj in json.loads(attestations)]
			except:
				numBlkHashPairs = []
			if aBlock!='null':
				if aBlockParent in blkParent:
					blkParent[aBlockParent].append(aBlock)
				else:
					blkParent[aBlockParent] = [aBlock]
					
				for pair in numBlkHashPairs:
					if pair[1] in blkAttestCount:
						if pair[0] > blkAttestCount[str(pair[1])]:
							blkAttestCount[str(pair[1])] = pair[0]
					else:
						blkAttestCount[str(pair[1])] = pair[0]
	blkList = list(set(   list(set(sum([*blkParent.values()],[])))    + [*blkParent.keys()]   ))#trick to get list of all block hashes #updated to also include keys (genesis or first block was getting missed)
	gedge = copy.deepcopy(blkParent)
	for blk in blkList:
		if blk not in gedge:
			gedge[blk] = []
	gedgenewnames = {}
	for blk in blkList:
		gedgenewnames[blk[0:10]+"  "+str(blkAttestCount.get(blk,0))+"A"] = [child[0:10]+"  "+str(blkAttestCount.get(child,0))+"A" for child in gedge[blk]]
	Graph(gedgenewnames,directed=True).plot()

def plotBeaconBlocks(hostNames,filePath):
	blkParent = {} #actually block children now
	blkAttestCount = {}
	blkSlot = {} #hash: slot
	
	numBlocksShown = 15 #shows this many of the most recent blocks
	
	for hostName in hostNames:
		
		try:
			daemonResponse = execOnDockerHost(hostName,"cat beaconBlocks.txt")
		except:
			print("Host "+hostName+" isnt recording beacon blocks")
			continue
		for line in daemonResponse[-1*numBlocksShown:]:
			blockItems = line.split(' ')
			aBlock = blockItems[0] #block hash
			aBlockParent = blockItems[1]
			aBlockSlot = blockItems[2]
			
			numBlkHashPairs = []
			if len(blockItems)>3 and blockItems[3]!='':
				attestations = blockItems[3].split('|')
				for attestation in attestations:
					if attestation != '':
						pair = attestation.split(',')
						pair[0] = int(pair[0])
						numBlkHashPairs.append(pair)
			
			
			if aBlockParent in blkParent:
				blkParent[aBlockParent].append(aBlock)
			else:
				blkParent[aBlockParent] = [aBlock]
				
			blkSlot[aBlock] = aBlockSlot
				
			for pair in numBlkHashPairs:
				if pair[1] in blkAttestCount:
					if pair[0] > blkAttestCount[str(pair[1])]:
						blkAttestCount[str(pair[1])] = pair[0]
				else:
					blkAttestCount[str(pair[1])] = pair[0]
	blkList = list(set(   list(set(sum([*blkParent.values()],[])))    + [*blkParent.keys()]   ))#trick to get list of all block hashes #updated to also include keys (genesis or first block was getting missed)
	gedge = copy.deepcopy(blkParent)
	for blk in blkList:
		if blk not in gedge:
			gedge[blk] = []
	gedgenewnames = {}
	for blk in blkList:
		gedgenewnames[blk[0:10]+"\n Slot: "+blkSlot[blk]+"\n"+str(blkAttestCount.get(blk,0))+" Attestations"] = [child[0:10]+"\n Slot: "+blkSlot[child]+"\n"+str(blkAttestCount.get(child,0))+" Attestations" for child in gedge[blk]]
	try:
		Graph(gedgenewnames,directed=True).plot(filePath)
	except:
		print("Empty plot for "+filePath);

def multiPlotBeaconBlocks(hostNames,folderName,numTimes,delayBetween):
	exec("rm -rf "+folderName);
	exec("mkdir "+folderName);
	ip = {}
	for hostName in hostNames:
		ip[hostName] = getIP(hostName)[0]
		exec("mkdir "+folderName+"/"+ip[hostName]);
	for i in range(numTimes):
		plotBeaconBlocks(hostNames,folderName+"/graph"+str(i)+".png")
		for hostName in hostNames:
			plotBeaconBlocks([hostName],folderName+"/"+ip[hostName]+"/graph"+str(i)+".png");
		if i!= numTimes-1:
			time.sleep(delayBetween)
	exec("eog "+folderName+"/graph0.png")
	

def interactiveBeaconBlockViewer(hostNames,validatorindexHost,ipTable,filePath,blockTimes,attackTimestamps):
	blkParent = {} #actually block: [children] now
	blkAttestCount = {}
	blkSlot = {} #hash: slot
	
	blkSltindex = {} #blockHash: [(slot, validator_index), ...]
	blkCommittProp = {} #blkHash: (proposerIndex, [(committeeIndex,[committeeValidatorIndex]),...] )
	
	for hostName in hostNames:
		
		try:
			daemonResponseProp = execOnDockerHost(hostName,"cat beaconProposers.txt")[0]
			ablkSltindex = json.loads(daemonResponseProp)
			blkSltindex = {**blkSltindex, **ablkSltindex}
		except:
			print("Host "+hostName+" isnt recording beacon proposers")
		
		try:
			daemonResponseCommitt = execOnDockerHost(hostName,"cat beaconCommittees.txt")[0]
			ablkCommittProp = json.loads(daemonResponseCommitt)
			blkCommittProp = {**blkCommittProp, **ablkCommittProp}
		except:
			print("Host "+hostName+" isnt recording beacon committees")
			
			
		
		try:
			daemonResponse = execOnDockerHost(hostName,"cat beaconBlocks.txt")
		except:
			print("Host "+hostName+" isnt recording beacon blocks")
			continue
		for line in daemonResponse:
			blockItems = line.split(' ')
			aBlock = blockItems[0] #block hash
			aBlockParent = blockItems[1]
			aBlockSlot = blockItems[2]
			
			numBlkHashPairs = []
			if len(blockItems)>3 and blockItems[3]!='':
				attestations = blockItems[3].split('|')
				for attestation in attestations:
					if attestation != '':
						pair = attestation.split(',')
						pair[0] = int(pair[0])
						numBlkHashPairs.append(pair)
			
			
			if aBlockParent in blkParent:
				blkParent[aBlockParent].append(aBlock)
			else:
				blkParent[aBlockParent] = [aBlock]
				
			blkSlot[aBlock] = aBlockSlot
			
			tempblkAttestCount = {}	
			for pair in numBlkHashPairs:
				if pair[1] in tempblkAttestCount:
					tempblkAttestCount[str(pair[1])] += pair[0]
				else:
					tempblkAttestCount[str(pair[1])] = pair[0]
			
			for pair in tempblkAttestCount.items():
				if pair[0] in blkAttestCount:
					if pair[1] > blkAttestCount[str(pair[0])]:
						blkAttestCount[str(pair[0])] = pair[1]
				else:
					blkAttestCount[str(pair[0])] = pair[1]
	
		
	
	
	blkList = list(set(   list(set(sum([*blkParent.values()],[])))    + [*blkParent.keys()]   ))#trick to get list of all block hashes #updated to also include keys (genesis or first block was getting missed)
	
	
	forks = getPaths(blkParent,'0x0000000000000000000000000000000000000000000000000000000000000000')
	ebbs = []
	edgeAttestations = {} #blkHash(for an edge (from,to), this is the to): edgeLabel 
	for fork in forks:
		forkReal = [blk for blk in fork if blk != '0x0000000000000000000000000000000000000000000000000000000000000000']
		forkBlkSlot = {key: blkSlot[key] for key in forkReal}
		#ebbs.extend(getEBBs(forkBlkSlot));
		#ebbs = list(set(ebbs))
		
		#This part adds attestation sums on edges so you can see which branch was heavier
	#New method for this (doesnt use fork so outside of loop)
	fillAttestationEdges(edgeAttestations,blkAttestCount,blkParent,'0x0000000000000000000000000000000000000000000000000000000000000000')
		#forkOrdered = order(blkSlot,forkReal)
		#for i in reversed(range(len(forkOrdered))):
		#	if not(forkOrdered[i] in edgeAttestations):
		#		edgeAttestations[forkOrdered[i]] = int(blkAttestCount.get(forkOrdered[i],0)) 
		#		if i < (len(forkOrdered)-1):
		#			edgeAttestations[forkOrdered[i]] = edgeAttestations[forkOrdered[i]] + edgeAttestations.get(forkOrdered[i+1],0)
		#	else:
		#		edgeAttestations[forkOrdered[i]] = edgeAttestations[forkOrdered[i]] + (0 if (i >= (len(forkOrdered)-1)) else edgeAttestations.get(forkOrdered[i+1],0))
	
	net = Network(layout = 'hierarchical',height="100vh", width="100%") #change 100vh to 750px if you want to see buttons
	for blk in blkList:
		if blk != '0x0000000000000000000000000000000000000000000000000000000000000000': #this value is null (the parent of genesis), not a real block
			
			#this section is for adding next proposers to plot
			propString = ""
			if blk in blkSltindex:
				propString = "\nNext Proposers:\n"
				for tupl in blkSltindex[blk]: #[(slot, validator_index), ...]
					slot = str(tupl[0])
					validatorI = int(tupl[1])
					validatorName = str(tupl[1])+"???\n"
					if validatorI in validatorindexHost:
						validatorName = validatorindexHost[validatorI]+"\n"+ipTable[validatorindexHost[validatorI]]+"\n"
					propString = propString + slot + ":\n" + validatorName + "\n"
					
			#this section is for adding committees to plot
			#for reference: blkCommittProp = {} #blkHash: (proposerIndex, [(committeeIndex,[committeeValidatorIndex]),...] )
			committString = ""
			currentProp = ""
			if blk in blkCommittProp:
				committString = "\nCommittees:\n"
				try:
					currentProp = "\nProposer:\n"+ipTable[validatorindexHost[int(blkCommittProp[blk][0])]]+"\n"
				except:
					currentProp = "\nProposer:\n"+str(blkCommittProp[blk][0])+"???\n"
				for tupl in blkCommittProp[blk][1]: #[(committeeIndex,[committeeValidatorIndex]),...]
					committeeIndex = "Committee #"+str(tupl[0])
					committString = committString + committeeIndex + ":\n"
					
					validators = tupl[1]
					for validatorI in validators:
						if int(validatorI) in validatorindexHost:
							validatorName = validatorindexHost[int(validatorI)]+"\n"+ipTable[validatorindexHost[int(validatorI)]]+",\n"
						else:
							validatorName = str(validatorI)+"???,\n"
						committString = committString + validatorName
					
					committString = committString + "\n"
			
			#adding blocks to plot, custom slot value will be used in x coord override
			try:
				net.add_node(blk, label=blk[0:10]+"\nSlot: "+blkSlot[blk]+"\nTimestamp:\n"+str(blockTimes.get(blk,"???"))+"\n"+str(blkAttestCount.get(blk,0))+" Attestations\n"+currentProp+committString+propString, shape = "box", color =  "#996083" if blk in ebbs else "#998060", slot = int(blkSlot[blk])*230)
			except KeyError:
				print("Key "+blk+" missing")
	
	#adding start and end time of disconnect attack
	anchorTime = -1
	anchorSlot = -1
	for blk in blkList:
			if blk in blockTimes and blk in blkSlot: #and blk in blkSlot is new
				anchorTime = blockTimes[blk]
				anchorSlot = blkSlot[blk]
				break; #break is new
	if anchorSlot != -1:
		for timestamp in attackTimestamps:
			net.add_node(str(timestamp[0]), label = str(timestamp[0])+"\nNetwork Disconnected", color = "#990000", shape = "circle", slot = (((timestamp[0]-anchorTime)/12.0) + int(anchorSlot))*230, y = 20)
			net.add_node(str(timestamp[1]), label = str(timestamp[1])+"\nNetwork Reconnected", color = "#009900", shape = "circle", slot = (((timestamp[1]-anchorTime)/12.0) + int(anchorSlot))*230, y = 20)
	
	try:
		edges = [(key, value) for key, values in blkParent.items() if key != '0x0000000000000000000000000000000000000000000000000000000000000000' for value in values]
		for edge in edges:
			try:
				labelStr = str(edgeAttestations[edge[0]]) #New changed 1 to 0
			except:
				labelStr = "???"
			net.add_edge(edge[0],edge[1],label=labelStr)
	except Exception as e:
		print("Error in plot for: ")
		print(hostNames)
		print(type(e).__name__)
		print(e)
		
	net.toggle_physics(False)
	#net.show_buttons()
	net.set_options("""
const options = {
  "edges": {
    "arrows": {
      "to": {
        "enabled": true,
        "scaleFactor": 1.35
      }
    },
    "arrowStrikethrough": true,
    "color": {
      "inherit": true
    },
    "font": {
      "size": 21,
      "strokeWidth": 4,
      "align": "middle"
    },
    "scaling": {
      "min": 4,
      "max": 20
    },
    "selfReferenceSize": null,
    "selfReference": {
      "angle": 0.7853981633974483
    },
    "smooth": false,
    "width": 1
  },
  "layout": {
  	"improvedLayout": false,
    "hierarchical": {
      "enabled": true,
      "levelSeparation": 230,
      "nodeSpacing": 200,
      "direction": "LR",
      "edgeMinimization": false,
      "treeSpacing": 400,
      "parentCentralization": false,
      "blockShifting": false,
      "sortMethod": "directed",
      "shakeTowards": "roots"
    }
  },
  "physics": {
  	"enabled": false
  }
  
  
  
}
""")

#If the physics is messing with something, turn it off by replacing the physics with this: has been replaced
	'''
  "physics": {
  	"hierarchicalRepulsion": {
      "centralGravity": 0,
      "avoidOverlap": null
    },
    "minVelocity": 0.75,
    "solver": "hierarchicalRepulsion"  	
  }
	'''
	

	net.save_graph(filePath+'.html')
	
	#custom x coord override
	with fileinput.FileInput(filePath+'.html', inplace=True, backup=False) as file:
		for line in file:
			print(line, end='')
			if 'network = new vis.Network(container, data, options);' in line:
				print('''network.on('beforeDrawing', function (ctx) {
					  var nodeId;
					  var node;
					  var pos;

					  for (nodeId in network.body.nodes) {
						if (network.body.nodes.hasOwnProperty(nodeId)) {
						  node = network.body.nodes[nodeId];
						  node.x = node.options.slot
						}
					  }
					});''');
	
	

def order(blkSlot,fork):
	return sorted(fork, key=lambda blkHash: int(blkSlot[blkHash]))
	
def fillAttestationEdges(edgeAttestations,blkAttestCount,blkParent,root,previousWeight=0):
	if root not in blkParent:
		return
	for child in blkParent[root]:
		if child in edgeAttestations:
			return
		edgeAttestations[child] = blkAttestCount.get(child,0) + previousWeight
		fillAttestationEdges(edgeAttestations,blkAttestCount,blkParent,child,edgeAttestations[child])
	
def getEBBs(blkSlot):
	slotBlks = {}
	for a,b in blkSlot.items():
		slotBlks[int(b)] = slotBlks.get(int(b),[])+[a]
	
	lastSlot = max([*slotBlks.keys()])
	ebbs = slotBlks[0]
	
	firstSlotInEpoch = 32
	while firstSlotInEpoch <= lastSlot:
		if firstSlotInEpoch in slotBlks:
			ebbs.extend(slotBlks[firstSlotInEpoch])
		else:
			mostRecentPrevBlk = firstSlotInEpoch -1
			while not (mostRecentPrevBlk in slotBlks):
				mostRecentPrevBlk -= 1
			ebbs.extend(slotBlks[mostRecentPrevBlk])
		firstSlotInEpoch += 32
	
	return list(set(ebbs))


def getPaths(tree,root):
	paths = []
	def dfs(node, current_path):
		if not tree.get(node):# leaf is where it is a value but not also a key, only use with blkParent
			paths.append(current_path + [node])
			return
			
		for child in list(set(tree[node])):
			dfs(child, current_path + [node])
			
	dfs(root, [])
	return paths	

def multiInteractiveBeaconBlocks(hostNames,validatorindexHost,ipTable,attackTimestamps,folderName,numTimes,delayBetween):
	exec("rm -rf "+folderName);
	exec("mkdir "+folderName);
	ip = {}
	for hostName in hostNames:
		ip[hostName] = getIP(hostName)[0]
		exec("mkdir "+folderName+"/"+ip[hostName]);
	for i in range(numTimes):
	
		#for getting block proposed timestamps
		blkTimesByHost = {}
		combinedBlkTimes = {}
		
		for hostName in hostNames:
			exec("mkdir "+folderName+"/"+ip[hostName]+"/logs"+str(i))
			try:
				execOnDockerHost(hostName,"cp /tmp/local-testnet/eth-*/beacon/logs/beacon.log beacon.log")
				exec("sudo docker cp "+hostName+":beacon.log ./"+folderName+"/"+ip[hostName]+"/logs"+str(i)+"/beacon.log")
				exec("sudo chmod 777 "+"./"+folderName+"/"+ip[hostName]+"/logs"+str(i)+"/beacon.log")
			except:
				pass
			try:
				execOnDockerHost(hostName,"cp /tmp/local-testnet/eth-*/validators/logs/validator.log validator.log")
				exec("sudo docker cp "+hostName+":validator.log ./"+folderName+"/"+ip[hostName]+"/logs"+str(i)+"/validator.log")
				exec("sudo chmod 777 "+"./"+folderName+"/"+ip[hostName]+"/logs"+str(i)+"/validator.log")
			except:
				pass
			
			ablkTimestamps = blkTimestamps("./"+folderName+"/"+ip[hostName]+"/logs"+str(i)+"/beacon.log")
			blkTimesByHost[hostName] = ablkTimestamps
			combinedBlkTimes = minDict(combinedBlkTimes,ablkTimestamps)
				
		interactiveBeaconBlockViewer(hostNames,validatorindexHost,ipTable,folderName+"/graph"+str(i),combinedBlkTimes,attackTimestamps)
		exec("firefox "+folderName+"/graph"+str(i)+".html")
		for hostName in hostNames:
			interactiveBeaconBlockViewer([hostName],validatorindexHost,ipTable,folderName+"/"+ip[hostName]+"/graph"+str(i),blkTimesByHost[hostName],attackTimestamps);
		if i!= numTimes-1:
			time.sleep(delayBetween)

def blkTimestamps(logFile):
	result = {} #blkhash: unixtime.fractionofsecond
	try:
		blockhashes = exec("cat "+logFile+" | grep \"New block received\" | grep -oP \"(?<=root: )[^,]+\"")
		blocktimes = exec("cat "+logFile+" | grep \"New block received\" | grep -oP \"\\K\\d+:\\d+:\\d+\\.\\d+\"")
		fullLines = exec("cat "+logFile+" | grep \"New block received\"")
		for i in range(len(fullLines)):
			segments = fullLines[i].split(' ')
			blkRecievedTime = int(datetime.strptime(""+str(datetime.now().year)+"-"+segments[0]+"-"+segments[1]+"|"+blocktimes[i],"%Y-%b-%d|%H:%M:%S.%f").replace(tzinfo=timezone.utc).timestamp()) + (int(blocktimes[i][-3:])/1000.0)
			result[blockhashes[i]] = blkRecievedTime
	except Exception as e:
		print(type(e).__name__)
		print(e)
		print("Error getting block times for a host, are there no blocks yet? Beacon API might also not be working")
	return result
		
def minDict(dict1, dict2):
    result = copy.deepcopy(dict1)
    for key, value in dict2.items():
        if key in result:
            result[key] = min(result[key], value)
        else:
            result[key] = value
    return result


def singleReorg(hostNames,offset=11,delayAmt = 25,isDelay=False):
	#Working Single Block Reorg on network where 50% of validators are in one as connected to another as with other 50%
	
	newBlockLineInLog = execOnDockerHost(hostNames[0],"cat tmp/local-testnet/eth-*/beacon/logs/beacon.log | grep \"New block received\" | tail -1")
	timestampItems = newBlockLineInLog[0].split(' ')
	newBlockTimeInBeaconLog = timestampItems[1]+" "+timestampItems[0]+" "+str(datetime.now().year)+" "+timestampItems[2][:-4];
	beaconBlockTime = time.mktime(time.strptime(newBlockTimeInBeaconLog, "%d %b %Y %H:%M:%S"))

	currentTime = time.mktime(time.localtime())
	timeDiff = currentTime - beaconBlockTime
	while timeDiff%12 != offset: #was 11
		time.sleep(0.5)
		currentTime = time.mktime(time.localtime())
		timeDiff = currentTime - beaconBlockTime
	startTime = time.time()
	print("Disconnected at "+str(startTime))
	#print(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime))
	
	#New topology to support more hosts
	delVec = [0]*delayVectorLen()
	
	#Old method with delay instead of disconnect keeps connections alive for some reason?
	if isDelay:
		#delayVector([int(delayAmt/2.0*1000.0),int(delayAmt/2.0*1000.0)]) #60000,60000 #was 12500,0
		delVec[-1] = int(delayAmt/2.0*1000.0)
		delVec[-2] = int(delayAmt/2.0*1000.0)
		delayVector(delVec)
	else:
		#New Method
		#disconnectVector([True,True])
		
		delVec[-1] = 1
		
		#newEnd = [1,1,0,0,1,1,0,1,1,0,1,1]
		#delVec[-1*len(newEnd):] = newEnd
		
		disconnectVector(delVec)
	
	time.sleep(delayAmt) #120 #was 12.5
	
	delVec = [0]*delayVectorLen()
	
	if isDelay:
		#Old method
		#delayVector([0,0])
		delayVector(delVec)
	else:
		#New Method
		#disconnectVector([False,False])
		disconnectVector(delVec)
	
	
	
	endTime = time.time()
	print("Reconnected at "+str(endTime))
	return (startTime,endTime)


def validatorIndices(hostNames):
	#Note can also get all validator index-pubkey with this endpoint: curl -X GET "http://10.0.254.245:8000/eth/v1/beacon/states/head/validators" -H  "accept: application/json" -sS | jq
	validatorindexHost = {}
	validatorindexPubkey = {}
	for hostName in hostNames:
		try:
			validatorindexLineInLog = execOnDockerHost(hostName,"cat tmp/local-testnet/eth-*/validators/logs/validator.log | grep \"Validator exists\" | tail -1")
			
			if (len(validatorindexLineInLog) != 1):
				print("Assertion failed in validatorIndices, found "+len(validatorindexLineInLog)+" lines in the log")
			else:
				line = validatorindexLineInLog[0]
				lineParts = line.replace(",","").replace(":","")
				lineParts = lineParts.split(' ') 
				validatorIndex = lineParts[lineParts.index("validator_index")+1]
				validatorPubkey = lineParts[lineParts.index("pubkey")+1]
				validatorindexHost[int(validatorIndex)] = hostName
				validatorindexPubkey[int(validatorIndex)] = validatorPubkey
		except:
			pass
	return (validatorindexHost,validatorindexPubkey)

def net0ipTable(hostNames):
	ipTable = {}
	for hostName in hostNames:
		ipTable[hostName] = getIP(hostName)[0]
	return ipTable

#hostNames = getHostNames();
#hostAddrs = getHostAddrs(hostNames);

#plotPeerGraph(hostNames,gethPeers,'Geth Peer Plot',False);
#plotPeerGraph(hostNames,beaconPeers,'Beacon Peer Plot',False);

#blkTimeDiffs = getBlockPropogationTimes(hostNames,False,False)
#fig, ax = plt.subplots()
#ax.ecdf(blkTimeDiffs)
#ax.set_xlabel('Block Propogation Delay (seconds)')
#ax.set_ylabel('Probability of Occurrence (CDF)')
#ax.set_title('CDF of Block Propogation Delays ')
#plt.show(block = False)

#blkTimeDiffs = getBlockPropogationTimes(hostNames,False,True)
#fig, ax = plt.subplots()
#ax.ecdf(blkTimeDiffs)
#ax.set_xlabel('Block Propogation Delay (seconds)')
#ax.set_ylabel('Probability of Occurrence (CDF)')
#ax.set_title('CDF of Block Propogation Delays with Delays Above 1s Removed')
#plt.show(block = False)

#plotBeaconBlocks(hostNames);

#plt.show() #Need this here at the end of the code because all the plt.show(block = False) statements hold onto their plots until this show here at the end which shows them all together




hostNames = getHostNames();
(validatorindexHost, _) = validatorIndices(hostNames)
ipTable = net0ipTable(hostNames)


#remove hosts that wont be logging:
newHostNames = []
for hostName in hostNames:
	if hostName in ipTable:
		nodeIP=ipTable[hostName]
		lastQuad = nodeIP.split(".")[-1]
		if lastQuad == '72':
			newHostNames.append(hostName)
hostNames = newHostNames

attackTimestamps = []
while True:
	try:
		if input("Plot beacon peers? (y/n)") == 'y':
			plotPeerGraph(hostNames,beaconPeers,'Beacon Peer Plot',True);
			plt.show()

		if input("Cause Reorg? (y/n)") == 'y':
			if input("Auto Attack? (y/n)") == 'y':
				numTimes = int(input("Num Times:"))
				minDelayBetween = int(input("Min time between attacks:"))
				for i in range(numTimes):
					(startTime,endTime) = singleReorg(hostNames,11,75,False)
					attackTimestamps.append((startTime,endTime))
					print("Waiting in between attacks")
					time.sleep(random.randint(minDelayBetween,minDelayBetween*2))
			else:
				try:
					isDelay = input("Disconnect(y) or Delay(n)?") == 'n'
					offset = int(input("Enter offset (default 11):"))
					delayAmt = float(input("Enter delay amount (default 25, max 548):"))
					if delayAmt>548:
						print("Delay above max, setting to 548")
						delayAmt = 548
					(startTime,endTime) = singleReorg(hostNames,offset,delayAmt,isDelay)
				except:
					print("Using defaults")
					(startTime,endTime) = singleReorg(hostNames)
				attackTimestamps.append((startTime,endTime))
		if input("Plot blockchain? (y/n)") == 'y':
			multiInteractiveBeaconBlocks(hostNames,validatorindexHost,ipTable,attackTimestamps,'ibeaconBlocks',1,60)
	except: # Exception as e:
		#print(type(e).__name__)
		#print(e)
		print(traceback.format_exc())
		if input("There was an error. Quit? (y/n)") == 'y':
			break


#multiPlotBeaconBlocks(hostNames,'beaconBlocks',30,10)




##Common docker curl beacon api cmd fmt: curl -X GET "http://10.6.254.250(get ip from ip addr):8000/lighthouse/analysis/attestation_performance/global?start_epoch=1&end_epoch=2" -H  "accept: application/json" -sS | jq
## sudo docker ps
## sudo docker exec -it CONTAINTERNAME /bin/bash
##reorgs are in warn of beacon logs


#for hostName in hostNames:
#	addDelay(hostName,0)






#for hostName in hostNames:
#    lines = execGethOnDockerHost(hostName, "eth.getBalance(eth.accounts[0])");
#    print(getIP(hostName)[0]+"'s account #0 balance: "+lines[-2])


#blkNum = 200
#minT = 0.0;
#minTOwn = "";
#for i in range(len(hostNames)):
##    try:
##        print("Tip proposed by: " + getBlockProposer(hostNames[i],hostAddrs,tipBlockNumber(hostNames[0])) );
##    except:
##        print(i)
#
#    try:
#        print("Container "+hostNames[i]+"'s chain says "+getBlockProposer(hostNames[i],hostAddrs,blkNum)+" proposed Block "+str(blkNum)+".")
#        t = getBlockRecievedTime(hostNames[i],blkNum)
#        print("It recieved that block at "+str(t))
#        if minT==0 or minT>t:
#            minT = t
#            minTOwn = hostNames[i]
#    except:
#        print(i)
#print("Min time was "+str(minT)+" by "+minTOwn)

#(blockNumbers,blockTimes) = getBlockTimes(hostNames[0],min(tipBlockNumber(hostNames[0]),100));
#fig, ax = plt.subplots()
#ax.bar(blockNumbers,blockTimes)
#ax.set_xlabel('Block Number')
#ax.set_ylabel('Block Time (seconds)')
#ax.set_title('Block Times')
#plt.show()
