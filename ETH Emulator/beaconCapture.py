import time
import subprocess
import json

def exec(cmd):
    letters = subprocess.check_output(cmd,shell=True, text=True)
    oneLine = "".join(letters)
    return oneLine.splitlines()
    
def execShell(cmd):
	return exec("/bin/bash -c \'"+cmd+"\'")
    
def getIP():#assumes net0 (the local network you specify in SEED when setting up network topology)
	try:
		return exec("ip -o -4 addr show dev net0 | grep -oP \"inet \\K[\\d.]+\"")[0]
	except:
		return exec("ip -o -4 addr show dev net1 | grep -oP \"inet \\K[\\d.]+\"")[0]
	
def tipBlockNumber():
	nodeIP = getIP()
	return int(execShell("curl -X GET \"http://"+nodeIP+":8000/eth/v1/beacon/headers/\" -H  \"accept: application/json\" -sS | jq \".data[].header.message.slot\"")[0].replace('"',''));

class Block:
	def __init__(self, hash, parent, slot, attestations):
		self.hash = hash
		self.parent = parent
		self.slot = slot
		self.attestations = attestations
	def __repr__(self):
	    return self.__str__()
	def __str__(self):
		return "{} {} {} {}".format(self.hash,self.parent,self.slot,self.attestations)

blocks = {} #hash: Block

def flush():
	blockFile = open("beaconBlocks.txt","w")
	for blk in [*blocks.values()]:
		blockFile.write(str(blk)+"\n")
	blockFile.close()

def combine(strarray):
	ret = ""
	for s in strarray:
		ret = ret + s
	return ret

def listSplit(execArr,sep):
	ret = []
	s = 0
	for i in range(len(execArr)):
		if execArr[i] == sep:
			ret.append(execArr[s:i])
			s = i+1
	return ret
	
def popcount16str(instr):
	return bin(int(instr,16)).count('1')
	
def getBeaconBlocks():
	tail = tipBlockNumber()
	head = max(tail - 10,0); #!!! If this node switches to a different fork, doesnt that mean a lot of blocks change for it and this method of only looking at 10 most recent blocks would miss all the new blocks from that fork if there is more than
	#10 from the new head to where the 2 forks diverged. Of course those blocks will be collected by other nodes who were on that fork already in the combined view so this is an issue for the individual view only
	
	nodeIP = getIP()
	
	someBlocks = listSplit(execShell("for i in {"+str(head)+".."+str(tail)+"}; do curl -X GET \"http://"+nodeIP+":8000/eth/v1/beacon/headers/?slot=$i\" -H  \"accept: application/json\" -sS | jq \".data[] | {root, \\\"parent\\\": .header.message.parent_root, \\\"slot\\\": .header.message.slot}\"; echo \"SEPERATOR\"; done"),"SEPERATOR");

	for i in range(len(someBlocks)-1):#-1 due to last seperator
		
		blockParentAsJSON = "["+combine(someBlocks[i]).replace("}{","},{")+"]";
		blockParent = [(obj["root"], obj["parent"], obj["slot"]) for obj in json.loads(blockParentAsJSON)]
		if blockParent:
			root = blockParent[0][0]
			parent = blockParent[0][1]
			slot = blockParent[0][2]
			
			attestations = execShell("curl -X GET \"http://"+nodeIP+":8000/eth/v1/beacon/blocks/"+root+"/attestations\" -H  \"accept: application/json\" -sS | jq \".data[] | {aggregation_bits, \\\"beacon_block_root\\\": .data.beacon_block_root}\"");
			try:
				attestationsAsJSON = "["+combine(attestations).replace("}{","},{")+"]";
				numBlkHashPairs = [(popcount16str(obj["aggregation_bits"]), obj["beacon_block_root"]) for obj in json.loads(attestationsAsJSON)]
			except:
				numBlkHashPairs = []
			
			numBlkHashPairsString = ""
			for pair in numBlkHashPairs:
				numAttestations = pair[0]
				associatedBlk = pair[1]
				numBlkHashPairsString += str(numAttestations)+","+associatedBlk+"|"
			
			blocks[root] = Block(root,parent,slot,numBlkHashPairsString)


blkSltindex = {} #blockHash: [(slot, validator_index), ...]
#!!! Possible issue if any of the future proposer data is changing for a given block over time for some reason this is only storing one set of values for each block. I dont think it is possible for this data to change though

def getBeaconProposers():
	nodeIP = getIP()
	
	aheadRequestNum = tipBlockNumber() + 10 #int((tipBlockNumber()/4.0) + 10)
	aheadRequest = execShell("curl -X GET \"http://"+nodeIP+":8000/eth/v1/validator/duties/proposer/"+str(aheadRequestNum)+"\" -H  \"accept: application/json\" -sS | jq \".message\"")[0].replace('"','');
	tail = int(aheadRequest.split(' ')[-1])+1
	head = max(tail - 10,0); #!!! basically the same warning as in getBeaconBlocks for this line
	
	someProposers = listSplit(execShell("for i in {"+str(head)+".."+str(tail)+"}; do curl -X GET \"http://"+nodeIP+":8000/eth/v1/validator/duties/proposer/$i\" -H  \"accept: application/json\" -sS | jq \".dependent_root, (.data[] | {validator_index,slot})\"; echo \"SEPERATOR\"; done"),"SEPERATOR");
	
	for i in range(len(someProposers)-1):#-1 due to last seperator
		blockHash = someProposers[i][0].replace('"','')
		slotIndexAsJSON = "["+combine(someProposers[i][1:]).replace("}{","},{")+"]";
		slotIndex = [(int(obj["slot"]), int(obj["validator_index"])) for obj in json.loads(slotIndexAsJSON)]
		blkSltindex[blockHash] = slotIndex

def flush2():
	propFile = open("beaconProposers.txt","w")
	json.dump(blkSltindex,propFile)
	propFile.close()

blkCommittProp = {} #blkHash: (proposerIndex, [(committeeIndex,[committeeValidatorIndex]),...] )	
def getBeaconCurrentBlkCommitteeAndProposer():
	tail = tipBlockNumber()
	head = max(tail - 10,0); #!!!
	
	nodeIP = getIP()
	
	someBlocks = listSplit(execShell("for i in {"+str(head)+".."+str(tail)+"}; do curl -X GET \"http://"+nodeIP+":8000/eth/v1/beacon/headers/?slot=$i\" -H  \"accept: application/json\" -sS | jq \".data[] | {root, \\\"slot\\\": .header.message.slot, \\\"proposer_index\\\": .header.message.proposer_index, \\\"state_root\\\": .header.message.state_root}\"; echo \"SEPERATOR\"; done"),"SEPERATOR");

	for i in range(len(someBlocks)-1):#-1 due to last seperator
		
		blockHeaderAsJSON = "["+combine(someBlocks[i]).replace("}{","},{")+"]";
		blockHeader = [(obj["root"], obj["slot"], obj["proposer_index"],obj["state_root"]) for obj in json.loads(blockHeaderAsJSON)]
		if blockHeader:
			root = blockHeader[0][0]
			slot = blockHeader[0][1]
			proposer_index = blockHeader[0][2]
			state_root = blockHeader[0][3]
			
			committees = execShell("curl -X GET \"http://"+nodeIP+":8000/eth/v1/beacon/states/"+state_root+"/committees?slot="+slot+"\" -H  \"accept: application/json\" -sS | jq \".data[] | {index,validators}\"");
			committeesAsJSON = "["+combine(committees).replace("}{","},{")+"]";
			committIndexValPairs = [(obj["index"], obj["validators"]) for obj in json.loads(committeesAsJSON)]
			
			blkCommittProp[root]=(proposer_index,committIndexValPairs)
			
def flush3():
	committeeFile = open("beaconCommittees.txt","w")
	json.dump(blkCommittProp,committeeFile)
	committeeFile.close()
			

#curl -X GET "http://10.0.254.245:8000/eth/v1/beacon/states/0xa91dc3c2ef020d7db096bd3a9772355dffa85425634116c688efcdb68ec6c6d0/committees?slot=263" -H  "accept: application/json" -sS | jq ".data[] | {index,validators}"
#curl -X GET "http://10.0.254.245:8000/eth/v1/beacon/headers/head" -H  "accept: application/json" -sS | jq ".data | {root,"slot": .header.message.slot, "proposer_index": .header.message.proposer_index, "state_root":.header.message.state_root }"

def shouldIRecord():
	nodeIP = getIP()
	lastQuad = nodeIP.split(".")[-1]
	#return  lastQuad == '254' or lastQuad == '253'
	return lastQuad == '72'
	#return True

if shouldIRecord():
	while True:
		try:
			getBeaconBlocks()
			getBeaconProposers()
			getBeaconCurrentBlkCommitteeAndProposer()
			flush()
			flush2()
			flush3()
		except:
			pass
		time.sleep(5)
