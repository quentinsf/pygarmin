#!/usr/bin/env python

import os,sys,time
import newstruct as struct
import serial
import math

# Set this value to > 0 for some debugging output, and the higher
# the number, the more you'll get.

debug = 0

# Introduction =====================================================

# There are 3 levels of protocol documented:
#
#       Application  (highest level)
#       Link
#       Physical     (lowest level)
#
# Garmin documents the various versions of these under labels of
# Pxxx, Lxxx, Axxx etc, and this convention is followed here.
# There are also various data types, named Dxxx.

# Roughly speaking, the Physical protocols specify RS232, the Link
# protocols specify a packet structure for sending messages to and
# fro, and the Application protocol specify what can actually go in
# those packets.


# secs from Unix epoch (start of 1970) to Sun Dec 31 00:00:00 1989

TimeEpoch = 631065600


# Physical protocols ===============================================

# See the Garmin docs for this. At the time of writing, the only
# documented physical layer is P000 which is roughly RS232 at 9600
# baud, 8 data bits, no parity, 1 stop bit. Unlike pure RS232, no
# negative voltages are used, but that is normally not too important.

# In software, we model this as something that has read and write
# methods, which can be used by the higher protocol levels. Later, we
# subclass this as something which handles Unix serial ports.


class P000:
	#" Physical layer for communicating with Garmin based on RS-232 "
	
	def read(self, n):
		pass
		
	def write(self, n):
		pass
		
# The following is handy for debugging:

#def hexdump(data): return ''.join(map(lambda x: "%02x" % ord(x), data)) or 
def hexdump(data): return ''.join(["%02x" % ord(x) for x in data])

# Define Errors

class GarminException:

	def __init__(self,data):
		self.data = data
	
class LinkException(GarminException):
		
	def __str__(self):
		return "Link Error"

class ProtocolException(GarminException):
		
	def __str__(self):
		return "Protocol Error"

# Link protocols ===================================================

#LinkException = "Link Error"

class L000:
	"Basic Link Protocol"
	Pid_Ack_Byte = 6
	Pid_Nak_Byte = 21
	Pid_Protocol_Array = 253
	Pid_Product_Rqst = 254
	Pid_Product_Data = 255

	# DataLinkEscape etc
	DLE                  = "\x10"
	ETX                  = "\x03"
	EOM                  = DLE+ETX

	def __init__(self, physicalLayer):
		self.phys = physicalLayer

	def sendPacket(self, ptype, data, readAck=1):
		" Send a message. By default this will also wait for the ack."
		
		if type(data) == type(""):
			ld = chr(len(data))
		else: # XXX assume 16-bit integer for now
			ld = chr(2)
			data = struct.pack("<h",data)
			
		tp = chr(ptype)
		chk = self.checksum( tp + ld + data)
		escline = self.escape( ld + data + chk)
		bytes = self.DLE + tp + escline + self.EOM
		self.phys.write(bytes)
		
		if debug > 5: print "< packet %3d : " % ptype, hexdump(data)
		
		if readAck:
			self.readAcknowledge(ptype)

	def readPacket(self, sendAck=1):
		" Read a message. By default this will also send the ack."
		
		dle = self.phys.read(1)
		
		# Find the start of a message
		
		while dle != self.DLE:
			print "resync - expected DLE and got something else"
			dle = self.phys.read(1)
			
		# We've now found either the start or the end of a msg
		# Try reading the type.
		
		tp = self.phys.read(1)
		
		# if it was the end
		
		if tp == self.ETX:
			dle = self.phys.read(1)
			tp = self.phys.read(1)
				 
		# Now we should be synchronised
		
		ptype = ord(tp)
		ld = self.readEscapedByte()
		datalen = ord(ld)
		data = ""
		
		for i in range(0, datalen):
			data = data + self.readEscapedByte()
			
		ck = self.readEscapedByte()
		
		if ck != self.checksum(tp + ld + data):
			raise LinkException, "Invalid checksum"
			
		eom = self.phys.read(2)
		assert(eom==self.EOM, "Invalid EOM seen")
		
		if debug > 5: print "> packet %3d : " % ptype, hexdump(data)
		
		if sendAck:
			self.sendAcknowledge(ptype)
			
		return (ptype, data)

	def expectPacket(self, ptype):
		"Expect and read a particular msg type. Return data."
		
		tp, data = self.readPacket()
		
		if tp != ptype:
			raise LinkException, "Expected msg type %d, got % 21 :d" % (ptype, tp)
			
		return data
	
	def readAcknowledge(self, ptype):
		"Read an ack msg in response to a particular sent msg"
		
		if debug > 5: print "(>ack)",
		
		# tp is the ack, data is only 1 byte and is the msg command number
		
		tp, data = self.readPacket(0)
			
		if (tp & 0xff) != self.Pid_Ack_Byte or ord(data[0]) != ptype:
			raise LinkException, "Acknowledge error"

	def sendAcknowledge(self, ptype):
	
		if debug > 5: print "(<ack)",
		
		self.sendPacket(self.Pid_Ack_Byte, struct.pack("<h", ptype), 0)

	def readEscapedByte(self):
		c = self.phys.read(1)
		
		if c == self.DLE:
			c = self.phys.read(1)
			
		return c
		
	def checksum(self, data):
		sum = 0
		
		for i in data:
			sum = sum + ord(i)
			
		sum = sum % 256
		return chr((256-sum) % 256)

	def escape(self, data):
		"Escape any DLE characters"
		
		#return string.join(string.split(data, self.DLE), self.DLE+self.DLE)
		return (self.DLE*2).join(data.split(self.DLE))
		

# L001 builds on L000

class L001(L000):
	"Link protocol 1"
	Pid_Command_Data = 10
	Pid_Xfer_Cmplt = 12
	Pid_Date_Time_Data = 14
	Pid_Position_Data = 17
	Pid_Prx_Wpt_Data = 19
	Pid_Records = 27
	Pid_Rte_Hdr = 29
	Pid_Rte_Wpt_Data = 30
	Pid_Almanac_Data = 31
	Pid_Trk_Data = 34
	Pid_Wpt_Data = 35
	Pid_Pvt_Data = 51
	Pid_Rte_Link_Data = 98
	Pid_Trk_Hdr = 99
	Pid_FlightBook_Record = 134		# packet with FlightBook data 
	Pid_Lap = 149									# part of Forerunner data 


# L002 builds on L000

class L002(L000):
	"Link Protocol 2"
	Pid_Almanac_Data = 4
	Pid_Command_Data = 11
	Pid_Xfer_Cmplt = 12
	Pid_Date_Time_Data = 20
	Pid_Position_Data = 24
	Pid_Prx_Wpt_Data = 27
	Pid_Records = 35
	Pid_Rte_Hdr = 37
	Pid_Rte_Wpt_Data = 39
	Pid_Wpt_Data = 43

# Application Protocols =======================================
	
# ProtocolException = "Protocol Error"

# A000 and A001 are used to find out what is on the other end of the
# wire, and hence which other protocols we can use.

class A000:
	"Product Data Protocol"

	def __init__(self, linkLayer):
		self.link = linkLayer

	def getProductData(self):
		fmt = "<hh"
		self.link.sendPacket(self.link.Pid_Product_Rqst,"")
		data = self.link.expectPacket(self.link.Pid_Product_Data)
		(prod_id, soft_ver)   = struct.unpack(fmt, data[:4])
		prod_descs = data[4:-1].split("\0")
		
		return (prod_id, soft_ver/100.0, prod_descs)


class A001:
	"Protocol Capabilities Protocol"

	def __init__(self, linkLayer):
		self.link=linkLayer
		
	def getProtocols(self):
		# may raise LinkException here
		
		if debug > 3: print "Try reading protocols using PCP"
		
		data = self.link.expectPacket(self.link.Pid_Protocol_Array)
		num = len(data)/3
		fmt = "<"+num*"ch"
		tup = struct.unpack(fmt, data)
		self.protocols = []
			
		for i in range(0, 2*num, 2):
			self.protocols.append(tup[i]+"%03d"%tup[i+1])
			
		if debug > 0:
			print "Protocols reported by A001:", self.protocols
			
		return self.protocols


	def getProtocolsNoPCP(self,prod_id, soft_ver):
	
		try:
			search_protocols = ModelProtocols[prod_id]
	
			for search_protocol in search_protocols:
				vrange = search_protocol[0]
		
				if ( (vrange == None) or
					 ((soft_ver >= vrange[0]) and (soft_ver < vrange[1]))):
					break
					
		except:
			raise "No protocols known for this software version. Strange!"
		
		# Ok, now we have de protocol
		
		self.protocols = [x for x in search_protocol[1:] if x]
		
		self.protocols.append("A700")
		self.protocols.append("D700")
		self.protocols.append("A800")
		self.protocols.append("D800")		
		
		return self.protocols
		
	"""
	def FormatA001(self):
		# This is here to get the list of strings returned by A001 into
		#the same format as used in the ModelProtocols dictionary

		try:
			phys = eval(self.protocols[0])
			link = eval(self.protocols[1])
			cmnd = eval(self.protocols[2])

			tuples = {"1" : None, "2" : None, "3" : None, "4" : None,
								"5" : None, "6" : None, "7" : None, "8" : None,
								"9" : None}
			last_seen = None
			
			for i in range(3, len(self.protocols)):
				p = self.protocols[i]
				
				if p[0] == "A":
					pclass = p[1]
					
					if tuples[pclass] == None:
						tuples[pclass] = []
						
					last_seen = tuples[pclass]
					
				last_seen.append(eval(p))
				
		except NameError:
			print sys.exc_info()[2]
			raise NameError, "Protocol %s not supported yet!" % sys.exc_info()[1]
			
		return (None, link, cmnd, tuples["1"], tuples["2"], tuples["3"],tuples["4"], tuples["5"])		
		"""
		
	def FormatA001(self):
		# This is here to get the list of strings returned by A001 into objects
		protos = {}
		protos_unknown = []
		known = None

		for x in self.protocols:

			if x == "P000":
				protos["phys"] = [eval(x)]
			elif x == "L001":
				protos["link"] = [eval(x)]
			elif x in ["A010","A011"]:
				protos["command"] = [eval(x)]
			elif x == "A100":
				known = True
				ap_prot = "waypoint" # Application Protocol
				protos[ap_prot] = [eval(x)]
			elif x in ["A200","A201"]:
				known = True
				ap_prot = "route"
				protos[ap_prot] = [eval(x)]
			elif x in ["A300","A301","A302"]:
				known = True
				ap_prot = "track"
				protos[ap_prot] = [eval(x)]
			elif x == "A400":
				known = True
				ap_prot = "proximity"
				protos[ap_prot] = [eval(x)]
			elif x == "A500":
				known = True
				ap_prot = "almanac"
				protos[ap_prot] = [eval(x)]
			elif x == "A600":
				known = True
				ap_prot = "data_time"
				protos[ap_prot] = [eval(x)]
			elif x == "A650":
				known = True
				ap_prot = "flightbook"
				protos[ap_prot] = [eval(x)]
			elif x == "A700":
				known = True
				ap_prot = "position"
				protos[ap_prot] = [eval(x)]
			elif x == "A800":
				known = True
				ap_prot = "pvt"
				protos[ap_prot] = [eval(x)]
			elif x == "A906":
				known = True
				ap_prot = "lap"
				protos[ap_prot] = [eval(x)]
			elif x[0] == "A":
				# No info about this Application Protocol
				known = False
				protos_unknown.append(x)
				
				if debug > 0:
					print "Protocol %s not supported yet!" %x
					
			elif (x[0] == "D"):
				if known:
					protos[ap_prot].append(eval(x))
				else:
					protos_unknown.append(x)
					
				
		if debug > 0:
			print "Processing protocols"
			print protos
			
		return protos,protos_unknown

	
# Commands  ---------------------------------------------------

class A010:
	"Device Command Protocol 1"
	Cmnd_Abort_Transfer = 0					# abort current transfer
	Cmnd_Transfer_Alm = 1     			# transfer almanac
	Cmnd_Transfer_Posn = 2    			# transfer position
	Cmnd_Transfer_Prx = 3     			# transfer proximity waypoints
	Cmnd_Transfer_Rte = 4     			# transfer routes
	Cmnd_Transfer_Time = 5    			# transfer time
	Cmnd_Transfer_Trk = 6     			# transfer track log   
	Cmnd_Transfer_Wpt = 7     			# transfer waypoints
	Cmnd_Turn_Off_Pwr = 8     			# turn off power
	Cmnd_Start_Pvt_Data = 49  			# start transmitting PVT data
	Cmnd_Stop_Pvt_Data = 50   			# stop transmitting PVT data
	Cmnd_FlightBook_Transfer = 92		# start transferring flight records
	Cmnd_Transfer_Laps = 117				# transfer laps

class A011:
	"Device Command Protocol 2"
	Cmnd_Abort_Transfer = 0   # abort current transfer
	Cmnd_Transfer_Alm = 4     # transfer almanacD800
	Cmnd_Transfer_Rte = 8     # transfer routes
	Cmnd_Transfer_Prx = 17		# transfer proximity waypoints
	Cmnd_Transfer_Time = 20   # transfer time
	Cmnd_Transfer_Wpt = 21    # transfer waypoints
	Cmnd_Turn_Off_Pwr = 26    # turn off power

# Transfer Protocols -------------------------------------------

# Most of the following protocols transfer groups of records of a
# particular format. The exact format depends on the product in use.
# Some records may have sub-groups within the transfer (eg. routes)
# each with their own header.

class TransferProtocol:

	def __init__(self, link, cmdproto, datatypes = None):
		self.link = link
		self.cmdproto = cmdproto
		
		if type(datatypes) == list:
			self.datatypes = datatypes
		else:
			self.datatypes = (datatypes,)
		
	def putData(self,callback,cmd,sendData):
	
		numrecords = len(sendData)
		x = 0
		
		if debug > 3: print self.__doc__, "Sending %d records" % numrecords
		
		self.link.sendPacket(self.link.Pid_Records, numrecords)
	
		for tp,data in sendData:
			self.link.sendPacket(tp, data.pack())
			
			if callback:
			
				try:
					x += 1
					callback(data,x,numrecords,tp)
				except:
					raise
			
		self.link.sendPacket(self.link.Pid_Xfer_Cmplt,cmd)	
		
	def abortTransfer(self):
		self.link.sendPacket(self.link.Pid_Command_Data,self.cmdproto.Cmnd_Abort_Transfer)
		
	def turnPowerOff(self):
		self.link.sendPacket(self.link.Pid_Command_Data,self.cmdproto.Cmnd_Turn_Off_Pwr)
			
class SingleTransferProtocol(TransferProtocol):

	def getData(self, callback, cmd, pid):
		self.link.sendPacket(self.link.Pid_Command_Data, cmd)
		data = self.link.expectPacket(self.link.Pid_Records)
		(numrecords,) = struct.unpack("<h", data)
		
		if debug > 3: print self.__doc__, "Expecting %d records" % numrecords
		
		result = []
		
		for i in range(numrecords):
			data = self.link.expectPacket(pid)
			p = self.datatypes[0]()
			p.unpack(data)
			result.append(str(p))
			
			if callback:
			
				try:
					callback(p,i + 1,numrecords,pid)
				except:
					raise
							
		self.link.expectPacket(self.link.Pid_Xfer_Cmplt)
		
		return result
	"""
	def putData(self, cmd, data_pid, records):
		numrecords = len(records)
		
		if debug > 3: print self.__doc__, "Sending %d records" % numrecords
		
		self.link.sendPacket(self.link.Pid_Records, numrecords)
		
		for i in records:
			self.link.sendPacket(data_pid, i.pack())
			
		self.link.sendPacket(self.link.Pid_Xfer_Cmplt, cmd)
	"""

class MultiTransferProtocol(TransferProtocol):

	def getData(self, callback, cmd, hdr_pid, *data_pids):
	
		self.link.sendPacket(self.link.Pid_Command_Data, cmd)
		
		data = self.link.expectPacket(self.link.Pid_Records)
		(numrecords,) = struct.unpack("<h", data)
		
		if debug > 3: print self.__doc__, "Expecting %d records" % numrecords
			
		data_pids = list(data_pids)
		result = []
		last = []
		
		for i in range(numrecords):
			tp, data = self.link.readPacket()
			
			if tp == hdr_pid:
			
				if last:
					result.append(last)
					last = []
					
				index = 0
			else:
				try:
					index = data_pids.index(tp) + 1
				except ValueError:
					raise ProtocolException, "Expected header or point"

			p = self.datatypes[index]()
			p.unpack(data)
			last.append(str(p))
				
			if callback:
				try:
					callback(p,i + 1,numrecords,tp)
				except:
					raise

		self.link.expectPacket(self.link.Pid_Xfer_Cmplt)
			
		if last:
			result.append(last)
				
		return result

# 
class T001:
	"no documentation as of 2004-02-24"
	pass
			
class A100(SingleTransferProtocol):
	"Waypoint Transfer Protocol"
	
	def getData(self, callback = None):
		return SingleTransferProtocol.getData(self, callback,
																					self.cmdproto.Cmnd_Transfer_Wpt,
																					self.link.Pid_Wpt_Data)
																					
	def putData(self,data,callback):
		sendData = []
		
		for waypoint in data:
			waypointInstance = self.datatypes[0](waypoint)
			sendData.append((self.link.Pid_Wpt_Data,waypointInstance))
		
		return SingleTransferProtocol.putData(self,callback,self.cmdproto.Cmnd_Transfer_Wpt,sendData)

class A200(MultiTransferProtocol):
	"Route Transfer Protocol"
														
	def getData(self, callback = None):
		return MultiTransferProtocol.getData(self, callback,
																				 self.cmdproto.Cmnd_Transfer_Rte,
																				 self.link.Pid_Rte_Hdr,
																				 self.link.Pid_Rte_Wpt_Data)
																			
	def putData(self,data,callback):
		sendData = []
		header = {}
		routenr = 0
		
		for route in data:
			routenr += 1
			
			# Copy the header fields
			
			header = {}
			
			for head in route[0].keys():
				header[head] = route[0][head]
			
			# Give a routenr	
			
			if not header.has_key('nmbr'): header['nmbr'] = routenr
			
			# Check route names
			# if no name, give it a name
			
			if not header.has_key('ident') or not header.has_key('cmnt'):	
			
				if header.has_key('ident'):
					header['cmnt'] = header['ident']
				elif header.has_key('cmnt'):
					header['ident'] = header['cmnt']
				else:
					header['ident'] = header['cmnt'] = "ROUTE " + str(routenr)
					
			headerInstance = self.datatypes[0](header)
			sendData.append((self.link.Pid_Rte_Hdr,headerInstance))
		
			for waypoint in route[1:]:
				waypointInstance = self.datatypes[1](waypoint)
				sendData.append((self.link.Pid_Rte_Wpt_Data,waypointInstance))
				
		return MultiTransferProtocol.putData(self,callback,self.cmdproto.Cmnd_Transfer_Rte,sendData)
																						
																					
class A201(MultiTransferProtocol):
	"Route Transfer Protocol"
	
	def getData(self, callback = None):
		return MultiTransferProtocol.getData(self, callback,
																				 self.cmdproto.Cmnd_Transfer_Rte,
																				 self.link.Pid_Rte_Hdr,
																				 self.link.Pid_Rte_Wpt_Data,
																				 self.link.Pid_Rte_Link_Data)
	def putData(self,data,callback):
		sendData = []
		header = {}
		routenr = 0
		
		for route in data:
			routenr += 1
			
			# Copy the header fields
			
			header = {}
			
			for head in route[0].keys():
				header[head] = route[0][head]
			
			# Give a routenr	
			
			if not header.has_key('nmbr'): header['nmbr'] = routenr
			
			# Check route names
			# if no name, give it a name
			
			if not header.has_key('ident') or not header.has_key('cmnt'):	
			
				if header.has_key('ident'):
					header['cmnt'] = header['ident']
				elif header.has_key('cmnt'):
					header['ident'] = header['cmnt']
				else:
					header['ident'] = header['cmnt'] = "Route " + str(routenr)
					
			headerInstance = self.datatypes[0](header)
			sendData.append((self.link.Pid_Rte_Hdr,headerInstance))
		
			for waypoint in route[1:]:
				waypointInstance = self.datatypes[1](waypoint)
				linkInstance = self.datatypes[2]()
				sendData.append((self.link.Pid_Rte_Wpt_Data,waypointInstance))
				sendData.append((self.link.Pid_Rte_Link_Data,linkInstance))
				
		return MultiTransferProtocol.putData(self,callback,self.cmdproto.Cmnd_Transfer_Rte,sendData)

class A300(SingleTransferProtocol):
	"Track Log Transfer Protocol"

	def getData(self, callback = None):
		return SingleTransferProtocol.getData(self, callback,
																					self.cmdproto.Cmnd_Transfer_Trk,
																					self.link.Pid_Trk_Data)

	def putData(self,data,callback):
		sendData = []
		
		for waypoint in data:
			waypointInstance = self.datatypes[0](waypoint)
			sendData.append((self.link.Pid_Trk_Data,waypointInstance))
		
		return SingleTransferProtocol.putData(self,callback,self.cmdproto.Cmnd_Transfer_Trk,sendData)
																																										
	
class A301(MultiTransferProtocol):
	"Track Log Transfer Protocol"
	
	def getData(self, callback = None):
		return MultiTransferProtocol.getData(self, callback,
																				 self.cmdproto.Cmnd_Transfer_Trk,
																				 self.link.Pid_Trk_Hdr,
																				 self.link.Pid_Trk_Data)
	def putData (self,data,callback):
		sendData = []
		header = {}
		tracknr = 0
		
		for track in data:
			tracknr += 1
			
			# Copy the header fields
			
			header = {}
			
			for head in track[0].keys():
				header[head] = track[0][head]
				
			# Check track names
			# if no name, give it a name
			
			if not header.has_key('ident'):
					header['ident'] = "TRACK" + str(tracknr)
			
			headerInstance = self.datatypes[0](header)
			sendData.append((self.link.Pid_Trk_Hdr,headerInstance))
			
			firstSegment = True
			
			for waypoint in track[1:]:
				trackPointInstance = self.datatypes[1](waypoint)
				
				# First point in a track is always a new track segment
				
				if firstSegment:
					trackPointInstance.dataDict['new_trk'] = True
					firstSegment = False
					
				sendData.append((self.link.Pid_Trk_Data,trackPointInstance))		
		
		return MultiTransferProtocol.putData(self,callback,self.cmdproto.Cmnd_Transfer_Trk,sendData)
		
class A302(A301):
	"Track Log Transfer Protocol"
	pass

class A400(SingleTransferProtocol):
	"Proximity Waypoint Transfer Protocol"
 
	def getData(self, callback = None):
		return SingleTransferProtocol.getData(self, callback,
																					self.cmdproto.Cmnd_Transfer_Prx,
																					self.link.Pid_Prx_Wpt_Data)
																					
	def putData(self,data,callback):
		sendData = []
		
		for waypoint in data:
			waypointInstance = self.datatypes[0](waypoint)
			sendData.append((self.link.Pid_Prx_Wpt_Data,waypointInstance))
		
		return SingleTransferProtocol.putData(self,callback,self.cmdproto.Cmnd_Transfer_Prx,sendData)
		

class A500(SingleTransferProtocol):
	"Almanac Transfer Protocol"
	
	def getData(self, callback):
		return SingleTransferProtocol.getData(self, callback,
																					self.cmdproto.Cmnd_Transfer_Alm,
																					self.link.Pid_Almanac_Data)
																					
class A600(TransferProtocol):
	"Waypoint Date & Time Initialization Protocol"
	
	def getData(self,callback):
		self.link.sendPacket(self.link.Pid_Command_Data,
												 self.cmdproto.Cmnd_Transfer_Time)
		data = self.link.expectPacket(self.link.Pid_Date_Time_Data)
		p = self.datatypes[0]() # p =D600()
		p.unpack(data)
		
		if callback:
			
			try:
				callback(p,1,1,self.link.Pid_Command_Data)
			except:
				raise

		return p
		
class A601(TransferProtocol):
	"Used by GPSmap 60cs, no specifications as of 2004-09-26"
	
	pass
		
class A650(SingleTransferProtocol):
	"FlightBook Transfer protocol"
	
	def getData(self,callback):
		return SingleTransferProtocol.getData(self, callback,
																					self.cmdproto.Cmnd_FlightBook_Transfer,
																					self.link.Pid_FlightBook_Record)

class A700(TransferProtocol):
	"Position Initialisation Protocol"
	pass

class A800(TransferProtocol):
	"PVT Data Protocol"
	
	# Live Position, Velocity and Time, similar to that provided by NMEA
	
	def dataOn(self):
		self.link.sendPacket(self.link.Pid_Command_Data,
												 self.cmdproto.Cmnd_Start_Pvt_Data)

	def dataOff(self):
		self.link.sendPacket(self.link.Pid_Command_Data,
												 self.cmdproto.Cmnd_Stop_Pvt_Data)

	def getData(self,callback):
	
		#data = self.link.expectPacket(self.link.Pid_Pvt_Data)
		# Otherwise Link Error: Expected msg type 51, got 114,
		# What type is 114 ?
		
		tp, data = self.link.readPacket()
		
		p = self.datatypes[0]()
		p.unpack(data)
		
		if callback:
			
			try:
				callback(p,1,1,tp)
			except:
				raise
		
		return p

class A801:
	"Used by ?, no documentation as of 2001-05-30"
	pass
	
class A802:
	"Used by ?, no documentation as of 2001-05-30"
	pass
	
class A900:
	"Used by GPS III+, no documentation as of 2000-09-18"
	pass
	
class A902:
	"Used by etrex, no documentation as of 2001-05-30"
	pass
	
class A903:
	"Used by etrex, no documentation as of 2001-05-30"
	pass

class A904:
	"no documentation as of 2004-02-24"
	pass
	
class A906(SingleTransferProtocol):
	"Lap Transfer protocol"
	
	def getData(self,callback):
		return SingleTransferProtocol.getData(self, callback,
																					self.cmdproto.Cmnd_Transfer_Laps,
																					self.link.Pid_Lap)

class A907(TransferProtocol):
	"Used by GPSmap 60cs, no documentation as of 2004-09-26"
	pass
	
# Most of the following subclasses have a fmt member which is a format
# string as understood by the struct module, detailing how the class
# is transmitted on the wire, and a 'parts' member, listing the
# atrributes that are serialized.

class DataPoint:
	parts = ()
	fmt = ""

	# Generic serialization stuff. If this looks complex, try it in
	# any other language!
	
	def pack(self):
		arg = (self.fmt,)
		
		for i in self.parts:
			#try:
				# I imagine this is faster, but it only works
				# if attribute 'i' has been assigned to. Otherwise
				# it's only in the class, not in the instance.
				#v = self.__dict__[i]
			#except KeyError:
				#v = eval('self.'+i)
			v = self.dataDict[i]	
			arg = arg + (v,)
			
		return apply(struct.pack, arg)

	def unpack(self, bytes):
		#print struct.calcsize(self.fmt), self.fmt
		#print len(bytes), repr(bytes)
		
		try:
			bits = struct.unpack(self.fmt, bytes)
			self.dataDict = {}
			
			for i in range(len(self.parts)):
				self.dataDict[self.parts[i]] = bits[i]
				#self.__dict__[self.parts[i]] = bits[i]
				
		except Exception, e:
			print e
			print "Format: <" + self.fmt   + ">"
			print "Parts:  <" + ", ".join(self.parts) + ">"
			#print "Parts:  <" + string.join(self.parts, ", ") + ">"
			print "Input:  <" + "><".join(bytes) + ">"
			#print "Input:  <" + string.join(bytes, "><") + ">"
			raise
			#raise Exception, e
			
	def getDict(self):
		return self.dataDict	
	
	
# Waypoints  ---------------------------------------------------

# Different products store different info in their waypoints
# Internally, waypoints store latitude and longitude in 'semicircle'
# coordinates. Here's the conversion:

def degrees(semi):
	return semi * 180.0 / (1L<<31)

def semi(deg):
	return long(deg * ((1L<<31) / 180))

def radian(semi):
	return semi * math.pi / (1L<<31)


# Distance between two waypoints (in metres)
# Haversine Formula (from R.W. Sinnott, "Virtues of the Haversine",
# Sky and Telescope, vol. 68, no. 2, 1984, p. 159):

def distance(wp1, wp2):
	R = 6367000
	rlat1 = radian(wp1.slat)
	rlon1 = radian(wp1.slon)
	rlat2 = radian(wp2.slat)
	rlon2 = radian(wp2.slon)
	dlon = rlon2 - rlon1
	dlat = rlat2 - rlon1
	a = math.pow(math.sin(dlat/2),2) + math.cos(rlat1)*math.cos(rlat2)*math.pow(math.sin(dlon/2),2)
	c = 2*math.atan2(math.sqrt(a), math.sqrt(1-a))
	return R*c
	
class Waypoint(DataPoint):
	"""
	parts = ("ident", "slat", "slon", "unused", "cmnt")
	fmt = "< 6s l l L 40s"

	def __init__(self, ident="", slat=0L, slon=0L, cmnt=""):
		self.ident = ident         # text identidier (upper case)
		self.slat = slat           # lat & long in semicircle terms
		self.slon = slon
		self.cmnt = cmnt           # comment (must be upper case)
		self.unused = 0L
	"""

	def __repr__(self):
		return "<Waypoint %s (%3.5f, %3.5f) (at %x)>" % (self.dataDict['ident'],
                                                     degrees(self.dataDict['slat']),
                                                     degrees(self.dataDict['slon']),
                                                     id(self))

	def __str__(self):
		return "%s (%3.5f, %3.5f)" % (self.dataDict['ident'],
                                  degrees(self.dataDict['slat']),
                                  degrees(self.dataDict['slon']))

class D100(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt")
	fmt = "< 6s l l L 40s"

	def __init__(self, data = {}):		
		self.dataDict = {}		
		self.dataDict['ident'] = ""         # text identidier (upper case)
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""           # comment (must be upper case)
		
		for x in data.keys():
			self.dataDict[x] = data[x]
			
class D101(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "dst", "smbl")
	fmt = "< 6s l l L 40s f b"

	def __init__(self, data = {}):		
		self.dataDict = {}		
		self.dataDict['ident'] = ""         # text identidier (upper case)
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""           # comment (must be upper case)
		self.dataDict['dst'] = 0.0
		self.dataDict['smbl'] = 0
		
		for x in data.keys():
			self.dataDict[x] = data[x]			


class D102(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "dst", "smbl")
	fmt = "< 6s l l L 40s f h"

	def __init__(self, data = {}):		
		self.dataDict = {}		
		self.dataDict['ident'] = ""         # text identidier (upper case)
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""           # comment (must be upper case)
		self.dataDict['dst'] = 0.0
		self.dataDict['smbl'] = 0
		
		for x in data.keys():
			self.dataDict[x] = data[x]						
			
class D103(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "smbl", "dspl")
	fmt = "< 6s l l L 40s b b"

	def __init__(self, data = {}):		
		self.dataDict = {}		
		self.dataDict['ident'] = ""         # text identidier (upper case)
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""           # comment (must be upper case)
		self.dataDict['smbl'] = 0
		self.dataDict['dspl'] = 0
		
		for x in data.keys():
			self.dataDict[x] = data[x]						
			
class D104(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "dst", "smbl", "dspl")
	fmt = "< 6s l l L 40s f h b"

	def __init__(self, data = {}):		
		self.dataDict = {}		
		self.dataDict['ident'] = ""         # text identidier (upper case)
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""           # comment (must be upper case)
		self.dataDict['dst'] = 0.0
		self.dataDict['smbl'] = 0
		self.dataDict['dspl'] = 0
		
		for x in data.keys():
			self.dataDict[x] = data[x]

class D105(Waypoint):
	parts = ("slat", "slon", "smbl", "ident")
	fmt = "<l l h s"

	def __init__(self, data = {}):		
		self.dataDict = {}		
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['smbl'] = 0
		self.dataDict['ident'] = ""         # text identidier (upper case)
		
		for x in data.keys():
			self.dataDict[x] = data[x]
			
class D106(Waypoint):
	parts = ("wpt_class", "subclass", "slat", "slon", "smbl", "ident", "lnk_ident")
	fmt = "<b 13s l l h s s"

	def __init__(self, data = {}):
		self.dataDict = {}		
		self.dataDict['wpt_class'] = 0
		self.dataDict['subclass'] = ""
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['smbl'] = 0
		self.dataDict['ident'] = ""
		self.dataDict['lnk_ident'] = ""
		
		for x in data.keys():
			self.dataDict[x] = data[x]
		
class D107(Waypoint):
	parts =	("ident", "slat", "slon", "unused", "cmnt",	"smbl", "dspl", "dst", "color")
	fmt = "<6s l l L 40s b b f b"
	
	def __init__(self, data = {}):
		self.dataDict = {}
		self.dataDict['ident'] = ""
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""
		self.dataDict['smbl'] = 0
		self.dataDict['dspl'] = 0
		self.dataDict['dst'] = 0.0
		self.dataDict['color'] = 0
		
		for x in data.keys():
			self.dataDict[x] = data[x]
			
						
class D108(Waypoint):
	parts = ("wpt_class", "color", "dspl", "attr", "smbl",
					 "subclass", "slat", "slon", "alt", "dpth", "dist",
					 "state", "cc", "ident", "cmnt", "facility", "city",
					 "addr", "cross_road")
	fmt = "<b b b b h 18s l l f f f 2s 2s s s s s s s"
		
	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['wpt_class'] = 0
		self.dataDict['color'] = 0
		self.dataDict['dspl'] = 0
		self.dataDict['attr'] = 0x60
		self.dataDict['smbl'] = 0
		self.dataDict['subclass'] = ""
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['alt'] = 1.0e25
		self.dataDict['dpth'] = 1.0e25
		self.dataDict['dist'] = 1.0e25
		self.dataDict['state'] = ""
		self.dataDict['cc'] = ""
		self.dataDict['ident'] = ""
		self.dataDict['cmnt'] = ""
		self.dataDict['facility'] = ""
		self.dataDict['city'] = ""
		self.dataDict['addr'] = ""
		self.dataDict['cross_road'] = ""
		
		for x in data.keys():
			self.dataDict[x] = data[x]
		
	def __str__(self):
		return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (
						self.dataDict['ident'],
						degrees(self.dataDict['slat']), degrees(self.dataDict['slon']),
						self.dataDict['alt'], string.strip(self.dataDict['cmnt']),
						self.dataDict['wpt_class'], self.dataDict['smbl'])									
	
class D109(Waypoint):
	parts = ("dtyp", "wpt_class", "dspl_color", "attr", "smbl",
					 "subclass", "slat", "slon", "alt", "dpth", "dist",
					 "state", "cc", "ete", "ident", "cmnt", "facility", "city",
					 "addr", "cross_road")
	fmt = "<b b b b h 18s l l f f f 2s 2s l s s s s s s"

	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['dtyp'] = 0x01
		self.dataDict['wpt_class'] = 0
		self.dataDict['dspl_color'] = 0
		self.dataDict['attr'] = 0x70
		self.dataDict['smbl'] = 18L
		self.dataDict['subclass'] = ""
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['alt'] = 1.0e25
		self.dataDict['dpth'] = 1.0e25
		self.dataDict['dist'] = 0.0
		self.dataDict['state'] = ""
		self.dataDict['cc'] = ""
		#self.dataDict['ete'] = 0xffffffff   # Estimated time en route in seconds to next waypoint
		self.dataDict['ete'] = -1   # Estimated time en route in seconds to next waypoint
		self.dataDict['ident'] = ""
		self.dataDict['cmnt'] = ""
		self.dataDict['facility'] = ""
		self.dataDict['city'] = ""
		self.dataDict['addr'] = ""
		self.dataDict['cross_road'] = ""		
		
		for x in data.keys():
			self.dataDict[x] = data[x]

	def __str__(self):
		return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (self.dataDict['ident'],
							degrees(self.dataDict['slat']),degrees(self.dataDict['slon']),
							self.dataDict['alt'],self.dataDict['cmnt'].strip(),
							self.dataDict['wpt_class'], self.dataDict['smbl'])	
							
class D110(Waypoint):
	parts = ("dtyp", "wpt_class", "dspl_color", "attr", "smbl",
					 "subclass", "slat", "slon", "alt", "dpth", "dist",
					 "state", "cc", "ete", "temp", "time", "wpt_cat",
					 "ident", "cmnt", "facility", "city", "addr", "cross_road")
	fmt = "<b b b b h 18s l l f f f 2s 2s l f l i s s s s s s"

	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['dtyp'] = 0x01
		self.dataDict['wpt_class'] = 0
		self.dataDict['dspl_color'] = 0
		self.dataDict['attr'] = 0x80
		self.dataDict['smbl'] = 18L
		self.dataDict['subclass'] = ""
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['alt'] = 1.0e25
		self.dataDict['dpth'] = 1.0e25
		self.dataDict['dist'] = 0.0
		self.dataDict['state'] = ""
		self.dataDict['cc'] = ""
		#self.dataDict['ete'] = 0xffffffff   # Estimated time en route in seconds to next waypoint
		self.dataDict['ete'] = -1   # Estimated time en route in seconds to next waypoint
		self.dataDict['temp'] = 1.0e25
		#self.dataDict['time'] = 0xffffffff
		self.dataDict['time'] = -1
		self.dataDict['wpt_cat'] =0x0000
		self.dataDict['ident'] = ""
		self.dataDict['cmnt'] = ""
		self.dataDict['facility'] = ""
		self.dataDict['city'] = ""
		self.dataDict['addr'] = ""
		self.dataDict['cross_road'] = ""		
		
		for x in data.keys():
			self.dataDict[x] = data[x]

	def __str__(self):
		return "%s (%3.5f, %3.5f, %3f) '%s' class %d symbl %d" % (self.dataDict['ident'],
							degrees(self.dataDict['slat']),degrees(self.dataDict['slon']),
							self.dataDict['alt'],self.dataDict['cmnt'].strip(),
							self.dataDict['wpt_class'], self.dataDict['smbl'])	
														
class D150(Waypoint):
	parts = ("ident", "cc", "wpt_class", "slat", "slon", "alt", "city", "state", "facility", "cmnt")
	fmt = "<6s 2s b l l i 24s 2s 30s 40s"
	
	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['ident'] = ""
		self.dataDict['cc'] = ""
		self.dataDict['wpt_class'] = 4 # user defined waipoint class
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['alt'] = 1.0e25
		self.dataDict['city'] = ""
		self.dataDict['state'] = ""
		self.dataDict['facility'] = ""
		self.dataDict['cmnt'] = ""
		
 		for x in data.keys():
			self.dataDict[x] = data[x]

class D151(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "dst", "facility", "city", "state", "alt", "cc", "unused2", "wpt_class")
	
	fmt = "< 6s l l L 40s f 30s 24s 2s i 2s c b"
	
	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['ident'] = ""
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""
		self.dataDict['dist'] = 0.0
		self.dataDict['facility'] = ""
		self.dataDict['alt'] = 1.0e25
		self.dataDict['city'] = ""
		self.dataDict['state'] = ""
		self.dataDict['cc'] = ""
		self.dataDict['unused2'] = ""
		self.dataDict['wpt_class'] = 2 # user defined waipoint class
		
 		for x in data.keysdspl():
			self.dataDict[x] = data[x]							

class D152(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "dst", "facility", "city", "state", "alt", "cc", "unused2", "wpt_class")
	
	fmt = "< 6s l l L 40s f 30s 24s 2s i 2s c b"
	
	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['ident'] = ""
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""
		self.dataDict['dist'] = 0.0
		self.dataDict['facility'] = ""
		self.dataDict['alt'] = 1.0e25
		self.dataDict['city'] = ""
		self.dataDict['state'] = ""
		self.dataDict['cc'] = ""
		self.dataDict['unused2'] = ""
		self.dataDict['wpt_class'] = 4 # user defined waipoint class
		
 		for x in data.keys():
			self.dataDict[x] = data[x]
								
class D154(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "dst", "facility", "city", "state", "alt", "cc", "unused2", "wpt_class", "smbl")
	
	fmt = "< 6s l l L 40s f 30s 24s 2s i 2s c b i"
	
	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['ident'] = ""
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""
		self.dataDict['dist'] = 0.0
		self.dataDict['facility'] = ""
		self.dataDict['alt'] = 1.0e25
		self.dataDict['city'] = ""
		self.dataDict['state'] = ""
		self.dataDict['cc'] = ""
		self.dataDict['unused2'] = ""
		self.dataDict['wpt_class'] = 4 # user defined waipoint class
		self.dataDict['smbl'] = 0
		
 		for x in data.keys():
			self.dataDict[x] = data[x]							
							
class D155(Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "dst", "facility", "city", "state", "alt", "cc", "unused2", "wpt_class", "smbl", "dspl")
	
	fmt = "< 6s l l L 40s f 30s 24s 2s i 2s c b i b"
	
	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['ident'] = ""
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""
		self.dataDict['dist'] = 0.0
		self.dataDict['facility'] = ""
		self.dataDict['alt'] = 1.0e25
		self.dataDict['city'] = ""
		self.dataDict['state'] = ""
		self.dataDict['cc'] = ""
		self.dataDict['unused2'] = ""
		self.dataDict['wpt_class'] = 4 # user defined waipoint class
		self.dataDict['smbl'] = 0
		self.dataDict['dspl'] = 3
		
 		for x in data.keys():
			self.dataDict[x] = data[x]							
										
# Route headers  ---------------------------------------------
		
class RouteHdr(DataPoint):
	
	def __repr__(self):
		return "<RouteHdr (at %x)>" % id(self)
		
class D200(RouteHdr):
	parts = ("nmbr",)
	fmt = "<b"

	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['nmbr'] = 0
		
		for x in data.keys():
			self.dataDict[x] = data[x]
			
	def __repr__(self):
		return "<RouteHdr %s (at %x)>" % (self.dataDict['nmbr'],id(self))			
		
	def __str__(self):
		return "%s" % (self.dataDict['nmbr'])

class D201(RouteHdr):
	parts = ("nmbr", "cmnt")
	fmt = "<b 20s"
	
	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['nmbr'] = 0
		self.dataDict['cmnt'] = ""
		
		for x in data.keys():
			self.dataDict[x] = data[x]
		
	def __repr__(self):
		return "<RouteHdr %s, %s (at %x)>" % (self.dataDict['nmbr'],self.dataDict['cmnt'],id(self))
		
	def __str__(self):
		return "%s, %s" % (self.dataDict['nmbr'],self.dataDict['cmnt'])		

class D202(RouteHdr):
	parts = ("ident",)
	fmt = "<s"

	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['ident'] = ""
		
		for x in data.keys():
			self.dataDict[x] = data[x]
		
	def __repr__(self):
		return "<RouteHdr %s at (%x)>" % (self.dataDict['ident'],id(self))
		
	def __str__(self):
		return "%s" % (self.dataDict['ident'])


# Route links  -----------------------------------------------

class RouteLink(DataPoint):
	
	def __repr__(self):
		return "<RouteLink (at %s)" % id(self)

class D210(RouteLink):
	parts = ("clazz", "subclass", "ident")
	fmt = "<h 18s s"
	
	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['clazz'] = 3
		self.dataDict['subclass'] = "\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff"
		self.dataDict['ident'] = ""

		for x in data.keys():
			self.dataDict[x] = data[x]

	def __repr__(self):
		return "<RouteLink %i, %s, %s (at %x) >" % (self.dataDict['clazz'],self.dataDict['subclass'],self.dataDict['ident'],id(self))		
		
	def __str__(self):
		return "%i, %s, %s" % (self.dataDict['clazz'],self.dataDict['subclass'],self.dataDict['ident'])

# Track points  ----------------------------------------------

class TrackPoint(DataPoint):
	# time = 0L # secs since midnight 31/12/89?

	def __repr__(self):
		return "<Trackpoint (%3.5f, %3.5f) %s (at %x)>" %\
						(degrees(self.dataDict['slat']), degrees(self.dataDict['slon']),
						time.asctime(time.gmtime(TimeEpoch+self.dataDict['time'])), id(self))

# Track points  ----------------------------------------------
	
class D300(TrackPoint):
	parts = ("slat", "slon", "time", "new_trk")
	fmt = "<l l L B"
	
	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['time'] = 0L
		self.dataDict['new_trk'] = False
		
		for x in data.keys():
			self.dataDict[x] = data[x]		
		
	def __str__(self):
		return "%3.5f, %3.5f, %s, %s" % (degrees(self.dataDict['slat']), degrees(self.dataDict['slon']),
																				time.asctime(time.gmtime(TimeEpoch+self.dataDict['time'])),
																				self.dataDict['new_trk'])

class D301(TrackPoint):
	parts = ("slat", "slon", "time", "alt", "depth", "new_trk")
	fmt = "<l l L f f b"
	 
	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['time'] = 0L
		self.dataDict['alt'] = 1.0e25
		self.dataDict['depth'] = 1.0e25
		self.dataDict['new_trk'] = False
		
		for x in data.keys():
			self.dataDict[x] = data[x]
		
	def __str__(self):
		return "%3.5f, %3.5f ,%s ,%s ,%s ,%s" % (degrees(self.dataDict['slat']), degrees(self.dataDict['slon']),
																				time.asctime(time.gmtime(TimeEpoch+self.dataDict['time'])),
																				self.dataDict['alt'],self.dataDict['depth'],self.dataDict['new_trk'])
																				
class D302(TrackPoint):
	parts = ("slat", "slon", "time", "alt", "depth", "temp", "new_trk")
	fmt = "<l l L f f f b"
	 
	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['time'] = 0L
		self.dataDict['alt'] = 1.0e25
		self.dataDict['depth'] = 1.0e25
		self.dataDict['temp'] = 1.0e25
		self.dataDict['new_trk'] = False
		
		for x in data.keys():
			self.dataDict[x] = data[x]
		
	def __str__(self):
		return "%3.5f, %3.5f ,%s ,%s ,%s ,%s,%s" % (degrees(self.dataDict['slat']), degrees(self.dataDict['slon']),
																				time.asctime(time.gmtime(TimeEpoch+self.dataDict['time'])),self.dataDict['alt'],
																				self.dataDict['depth'],self.dataDict['temp'],self.dataDict['new_trk'])
		
# Track headers ----------------------------------------------

class TrackHdr(DataPoint):

	def __repr__(self):
		return "<TrackHdr %s (at %x)>" % (self.dataDict['ident'],id(self))

class D310(TrackHdr):
	parts = ("dspl", "color", "ident")
	fmt = "<b b s"
	
	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['dspl'] = False
		self.dataDict['color'] = -1
		self.dataDict['ident'] = ""
		
		for x in data.keys():
			self.dataDict[x] = data[x]		
		
	def __str__(self):
		return "%s, %s, %s" % (self.dataDict['dspl'],self.dataDict['color'],self.dataDict['ident'])
		
class D311(TrackHdr):
	parts = ("index",)
	fmt = "<H"

	""" 
	Code not used because we can't send info to the gps
	but somebody can always try
	
	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['index'] = 0
		
		for x in data.keys():
			self.dataDict[x] = data[x]	
	"""
		
	def __str__(self):
		return "%s" % (self.dataDict['index'])
		
class D312(TrackHdr):
	parts = ("dspl", "color", "ident")
	fmt = "<b b s"
	
	def __init__(self,data = {}):
		self.dataDict = {}
		self.dataDict['dspl'] = False
		self.dataDict['color'] = -1
		self.dataDict['ident'] = ""
		
		for x in data.keys():
			self.dataDict[x] = data[x]		
		
	def __str__(self):
		return "%s, %s, %s" % (self.dataDict['dspl'],self.dataDict['color'],self.dataDict['ident'])

# Proximity waypoints  ---------------------------------------

class ProxPoint:

	def __repr__(self):
		return "<Proximity waypoints %s (at %x)>" % (self.dataDict['ident'],id(self))
	
	def __str__(self):
		return "%s (%3.5f, %3.5f) %3.5f" % (self.dataDict['ident'],
                                  degrees(self.dataDict['slat']),
                                  degrees(self.dataDict['slon']),
																	self.dataDict['dst'])
		
class D400(ProxPoint,Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "dst")
	fmt = "< 6s l l L 40s f"

	def __init__(self, data = {}):		
		self.dataDict = {}		
		self.dataDict['ident'] = ""         # text identidier (upper case)
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""           # comment (must be upper case)
		self.dataDict['dst'] = 0.0
		
		for x in data.keys():
			self.dataDict[x] = data[x]
			
class D403(ProxPoint,Waypoint):
	parts = ("ident", "slat", "slon", "unused", "cmnt", "smbl", "dspl", "dst")
	fmt = "< 6s l l L 40s b b f"

	def __init__(self, data = {}):		
		self.dataDict = {}		
		self.dataDict['ident'] = ""         # text identidier (upper case)
		self.dataDict['slat'] = 0L           # lat & long in semicircle terms
		self.dataDict['slon'] = 0L
		self.dataDict['unused'] = 0L
		self.dataDict['cmnt'] = ""           # comment (must be upper case)
		self.dataDict['smbl'] = 0
		self.dataDict['dspl'] = 0
		self.dataDict['dst'] = 0.0
		
		for x in data.keys():
			self.dataDict[x] = data[x]						

class D450(ProxPoint,Waypoint):
	parts = ("idx", "ident", "cc", "wpt_class", "slat", "slon", "alt", "city", "state", "facility", "cmnt", "dst")
	fmt = "<i 6s 2s b l l i 24s 2s 30s 40s f "
	
	def __init__(self, data = {}):		
		self.dataDict = {}
		self.dataDict['idx'] = 0
		self.dataDict['ident'] = ""
		self.dataDict['cc'] = ""
		self.dataDict['wpt_class'] = 4 # user defined waipoint class
		self.dataDict['slat'] = 0L
		self.dataDict['slon'] = 0L
		self.dataDict['alt'] = 1.0e25
		self.dataDict['city'] = ""
		self.dataDict['state'] = ""
		self.dataDict['facility'] = ""
		self.dataDict['cmnt'] = ""
		self.dataDict['dst'] = 0.0
		
 		for x in data.keys():
			self.dataDict[x] = data[x]						
	
# Almanacs ---------------------------------------------------

class Almanac(DataPoint):

	def __repr__(self):
		return "<Almanax> (at %x) " % id(self)
		
	def __str__(self):
		return "Working on progress"
		#return "%s" % self.dataDict['weeknum']
		
class D500(Almanac):
	parts = ("weeknum", "toa", "af0", "af1", "e",
					 "sqrta", "m0", "w", "omg0", "odot", "i")
	fmt = "<i f f f f f f f f f f"

class D501(Almanac):
	parts = ("weeknum", "toa", "af0", "af1", "e",
					 "sqrta", "m0", "w", "omg0", "odot", "i", "hlth")
	fmt = "<i f f f f f f f f f f b"

class D550(Almanac):
	parts = ("svid", "weeknum", "toa", "af0", "af1", "e",
					 "sqrta", "m0", "w", "omg0", "odot", "i")
	fmt = "<c i f f f f f f f f f f"

class D551(Almanac):
	parts = ("svid", "weeknum", "toa", "af0", "af1", "e",
					 "sqrta", "m0", "w", "omg0", "odot", "i", "hlth")
	fmt = "<c i f f f f f f f f f f b"

# Date & Time  ---------------------------------------------------

class TimePoint(DataPoint):
	# Not sure what the last four bytes are. Not in docs.
	# hmm... eTrex just sends 8 bytes, no trailing 4 bytes
	
	def __repr__(self):
		return "<Date/Time (at %x)>" % id(self)
	
class D600(TimePoint):
	parts = ("month", "day", "year", "hour", "min", "sec") #,"unknown")
	fmt = "<b b H h b b" #L"
	"""
	month = 0         # month (1-12)
	day = 0           # day (1-32)
	year = 0          # year
	hour = 0          # hour (0-23)
	min = 0           # min (0-59)
	sec = 0           # sec (0-59)
	"""
		
	def __str__(self):
		return "%d-%.2d-%.2d %.2d:%.2d:%.2d UTC" % (
						self.dataDict['year'], self.dataDict['month'], self.dataDict['day'],
						self.dataDict['hour'], self.dataDict['min'], self.dataDict['sec'])
						
class D601(TimePoint):
	"used by GPSmap 60cs, no documentation as of 2004-09-26"
	pass						
						
# FlightBook

class D650(DataPoint):
	parts = ("takeoff_time", "landing_time", "takeoff_lat", "takeoff_lon",
					 "landing_lat", "landing_lon", "night_time", "num_landings",
					 "max_speed", "max_alt", "distance", "cross_country_flag",
					 "departure_name", "departure_ident", "arrival_name",
					 "arrival_ident", "ac_id")
	fmt = "<L L l l l l L L f f f B s s s s s"
	
	def __str__(self):
		return "%s %s takeoff: (%s,%s) landing: (%s,%s)" % (self.dataDict['takeoff_time'],self.dataDict['landing_time'],
											self.dataDict['takeoff_lat'],self.dataDict['takeoff_lon'],
											self.dataDict['landing_lat'],self.dataDict['landing_lon'])
											
class D700:
	pass
	
# Live position info

class D800(DataPoint):
	parts = ("alt", "epe", "eph", "epv", "fix", "tow", "rlat", "rlon",
					 "east", "north", "up", "msl_height", "leap_secs", "wn_days")
	fmt = "<f f f f h d d d f f f f h l"
	
	def __repr__(self):
		return "<Live position (at %x) " % id(self)
		
	def __str__(self):
		return "tow: %g rlat: %g rlon: %g east: %g north %g" \
						% (self.dataDict['tow'], self.dataDict['rlat'],
							 self.dataDict['rlon'], self.dataDict['east'], self.dataDict['north'])
		
class D801:
	pass

class D802:
	pass
	
# Lap type 

class D906(DataPoint):
	parts = ("start_time", "total_time", "total_distance", "begin_lat", "begin_lon",
					 "end_lat", "end_lon", "calories", "track_index", "unused")
	fmt = "<L L f l l l l H B B"
	
	def __str__(self):
		return "start: %s total: %s begin: (%s,%s) end: (%s,%s) index: %s" % (self.dataDict['start_time'],
							self.dataDict['total_time'],self.dataDict['begin_lat'],self.dataDict['begin_lon'],
							self.dataDict['end_lat'],self.dataDict['end_lon'],self.dataDict['track_index'])

class D907(DataPoint):
	"used by GPSmap 60cs, no documentation as of 2004-09-26"
	pass
	
class D908(DataPoint):
	"used by GPSmap 60cs, no documentation as of 2004-09-26"
	pass
	
class D910(DataPoint):
	"used by GPSmap 60cs, no documentation as of 2004-09-26"
	pass	
	
		
# Garmin models ==============================================

# For reference, here are some of the product ID numbers used by
# different Garmin models. Notice that this is not a one-to-one
# mapping in either direction!

ModelIDs = (
	(52, "GNC 250"),
	(64, "GNC 250 XL"),
	(33, "GNC 300"),
	(98, "GNC 300 XL"),
	(77, "GPS 12"),
	(87, "GPS 12"),
	(96, "GPS 12"),
	(77, "GPS 12 XL"),
	(96, "GPS 12 XL"),
	(106, "GPS 12 XL Chinese"),
	(105, "GPS 12 XL Japanese"),
	(47, "GPS 120"),
	(55, "GPS 120 Chinese"),
	(74, "GPS 120 XL"),
	(61, "GPS 125 Sounder"),
	(95, "GPS 126"),
	(100, "GPS 126 Chinese"),
	(95, "GPS 128"),
	(100, "GPS 128 Chinese"),
	(20, "GPS 150"),
	(64, "GPS 150 XL"),
	(34, "GPS 155"),
	(98, "GPS 155 XL"),
	(34, "GPS 165"),
	(41, "GPS 38"),
	(56, "GPS 38 Chinese"),
	(62, "GPS 38 Japanese"),
	(31, "GPS 40"),
	(41, "GPS 40"),
	(56, "GPS 40 Chinese"),
	(62, "GPS 40 Japanese"),
	(31, "GPS 45"),
	(41, "GPS 45"),
	(56, "GPS 45 Chinese"),
	(41, "GPS 45 XL"),
	(96, "GPS 48"),
	(7,  "GPS 50"),
	(14, "GPS 55"),
	(15, "GPS 55 AVD"),
	(18, "GPS 65"),
	(13, "GPS 75"),
	(23, "GPS 75"),
	(42, "GPS 75"),
	(25, "GPS 85"),
	(39, "GPS 89"),
	(45, "GPS 90"),
	(112, "GPS 92"),
	(24, "GPS 95"),
	(35, "GPS 95"),
	(22, "GPS 95 AVD"),
	(36, "GPS 95 AVD"),
	(36, "GPS 95 XL"),
	(59, "GPS II"),
	(73, "GPS II Plus"),
	(97, "GPS II Plus"),
	(72, "GPS III"),
	(71, "GPS III Pilot"),
	(50, "GPSCOM 170"),
	(53, "GPSCOM 190"),
	(49, "GPSMAP 130"),
	(76, "GPSMAP 130 Chinese"),
	(49, "GPSMAP 135 Sounder"),
	(49, "GPSMAP 175"),
	(48, "GPSMAP 195"),
	(29, "GPSMAP 205"),
	(44, "GPSMAP 205"),
	(29, "GPSMAP 210"),
	(88, "GPSMAP 215"),
	(29, "GPSMAP 220"),
	(88, "GPSMAP 225"),
	(49, "GPSMAP 230"),
	(76, "GPSMAP 230 Chinese"),
	(49, "GPSMAP 235 Sounder")
)
	
# Make sure you've got a really wide window to view this one!
# This describes the protocol capabilities of products that do not
# support the Protocol Capabilities Protocol (most of them).  Some
# models differ in capabilities depending on the software version
# installed. So for each ID there is a tuple of entries. Each entry
# begins with either None, if it applies to all versions with that ID,
# or (minv, maxv), meaning that it applies if the software version
# >= minv and < maxv.

# All models implement A000, A600 and A700

MaxVer = 999.99

ModelProtocols = {
#                        Use a wide window for best viewing!
#
# ID    minver maxver    Link     Cmnd   Wpt,            Rte,                    Trk,             Prx,           Alm
7:   ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", None,           None,           "A500", "D500" ), ),
13:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
14:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", None,           "A400", "D400", "A500", "D500" ), ),
15:  ( (None,            "L001", "A010", "A100", "D151", "A200", "D200", "D151", None,           "A400", "D151", "A500", "D500" ), ),
18:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
20:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D550" ), ),
22:  ( (None,            "L001", "A010", "A100", "D152", "A200", "D200", "D152", "A300", "D300", "A400", "D152", "A500", "D500" ), ),
23:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
24:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
25:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
29:  ( ((0.00, 4.00),    "L001", "A010", "A100", "D101", "A200", "D201", "D101", "A300", "D300", "A400", "D101", "A500", "D500" ),
       ((4.00, MaxVer),  "L001", "A010", "A100", "D102", "A200", "D201", "D102", "A300", "D300", "A400", "D102", "A500", "D500" ), ),
31:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None    ,       "A500", "D500" ), ),
33:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D550" ), ),
34:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D550" ), ),
35:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
36:  ( ((0.00, 3.00),    "L001", "A010", "A100", "D152", "A200", "D200", "D152", "A300", "D300", "A400", "D152", "A500", "D500" ),
       ((3.00, MaxVer),  "L001", "A010", "A100", "D152", "A200", "D200", "D152", "A300", "D300", None,           "A500", "D500" ), ),
39:  ( (None,            "L001", "A010", "A100", "D151", "A200", "D201", "D151", "A300", "D300", None,           "A500", "D500" ), ),
41:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
42:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D200", "D100", "A300", "D300", "A400", "D400", "A500", "D500" ), ),
44:  ( (None,            "L001", "A010", "A100", "D101", "A200", "D201", "D101", "A300", "D300", "A400", "D101", "A500", "D500" ), ),
45:  ( (None,            "L001", "A010", "A100", "D152", "A200", "D201", "D152", "A300", "D300", None,           "A500", "D500" ), ),
47:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
48:  ( (None,            "L001", "A010", "A100", "D154", "A200", "D201", "D154", "A300", "D300", None,           "A500", "D501" ), ),
49:  ( (None,            "L001", "A010", "A100", "D102", "A200", "D201", "D102", "A300", "D300", "A400", "D102", "A500", "D501" ), ),
50:  ( (None,            "L001", "A010", "A100", "D152", "A200", "D201", "D152", "A300", "D300", None,           "A500", "D501" ), ),
52:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D550" ), ),
53:  ( (None,            "L001", "A010", "A100", "D152", "A200", "D201", "D152", "A300", "D300", None,           "A500", "D501" ), ),
55:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
56:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
59:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
61:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
62:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
64:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D551" ), ),
71:  ( (None,            "L001", "A010", "A100", "D155", "A200", "D201", "D155", "A300", "D300", None,           "A500", "D501" ), ),
72:  ( (None,            "L001", "A010", "A100", "D104", "A200", "D201", "D104", "A300", "D300", None,           "A500", "D501" ), ),
73:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", None,           "A500", "D501" ), ),
74:  ( (None,            "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", None,           "A500", "D500" ), ),
76:  ( (None,            "L001", "A010", "A100", "D102", "A200", "D201", "D102", "A300", "D300", "A400", "D102", "A500", "D501" ), ),
77:  ( ((0.00, 3.01),    "L001", "A010", "A100", "D100", "A200", "D201", "D100", "A300", "D300", "A400", "D400", "A500", "D501" ),
       ((3.01, 3.50),    "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ),
       ((3.50, 3.61),    "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", None,           "A500", "D501" ),
       ((3.61, MaxVer),  "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
87:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
88:  ( (None,            "L001", "A010", "A100", "D102", "A200", "D201", "D102", "A300", "D300", "A400", "D102", "A500", "D501" ), ),
95:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
96:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
97:  ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", None,           "A500", "D501" ), ),
98:  ( (None,            "L002", "A011", "A100", "D150", "A200", "D201", "D150", None,           "A400", "D450", "A500", "D551" ), ),
100: ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
105: ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
106: ( (None,            "L001", "A010", "A100", "D103", "A200", "D201", "D103", "A300", "D300", "A400", "D403", "A500", "D501" ), ),
112: ( (None,            "L001", "A010", "A100", "D152", "A200", "D201", "D152", "A300", "D300", None,           "A500", "D501" ), )
}

''' Old table, making strings of it 
ModelProtocols = {
#                        Use a wide window for best viewing!
#
# ID    minver maxver    Link  Cmnd   Wpt,          Rte,                Trk,          Prx,          Alm
7:   ( (None,            L001, A010, (A100, D100), (A200, D200, D100), None,         None,         (A500, D500) ), ),
13:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
14:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), None,         (A400, D400), (A500, D500) ), ),
15:  ( (None,            L001, A010, (A100, D151), (A200, D200, D151), None,         (A400, D151), (A500, D500) ), ),
18:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
20:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
22:  ( (None,            L001, A010, (A100, D152), (A200, D200, D152), (A300, D300), (A400, D152), (A500, D500) ), ),
23:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
24:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
25:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
29:  ( ((0.00, 4.00),    L001, A010, (A100, D101), (A200, D201, D101), (A300, D300), (A400, D101), (A500, D500) ),
       ((4.00, MaxVer),  L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D500) ), ),
31:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
33:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
34:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
35:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
36:  ( ((0.00, 3.00),    L001, A010, (A100, D152), (A200, D200, D152), (A300, D300), (A400, D152), (A500, D500) ),
       ((3.00, MaxVer),  L001, A010, (A100, D152), (A200, D200, D152), (A300, D300), None,         (A500, D500) ), ),
39:  ( (None,            L001, A010, (A100, D151), (A200, D201, D151), (A300, D300), None,         (A500, D500) ), ),
41:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
42:  ( (None,            L001, A010, (A100, D100), (A200, D200, D100), (A300, D300), (A400, D400), (A500, D500) ), ),
44:  ( (None,            L001, A010, (A100, D101), (A200, D201, D101), (A300, D300), (A400, D101), (A500, D500) ), ),
45:  ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D500) ), ),
47:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
48:  ( (None,            L001, A010, (A100, D154), (A200, D201, D154), (A300, D300), None,         (A500, D501) ), ),
49:  ( (None,            L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D501) ), ),
50:  ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D501) ), ),
52:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D550) ), ),
53:  ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D501) ), ),
55:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
56:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
59:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
61:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
62:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
64:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D551) ), ),
71:  ( (None,            L001, A010, (A100, D155), (A200, D201, D155), (A300, D300), None,         (A500, D501) ), ),
72:  ( (None,            L001, A010, (A100, D104), (A200, D201, D104), (A300, D300), None,         (A500, D501) ), ),
73:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), None,         (A500, D501) ), ),
74:  ( (None,            L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), None,         (A500, D500) ), ),
76:  ( (None,            L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D501) ), ),
77:  ( ((0.00, 3.01),    L001, A010, (A100, D100), (A200, D201, D100), (A300, D300), (A400, D400), (A500, D501) ),
       ((3.01, 3.50),    L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ),
       ((3.50, 3.61),    L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), None,         (A500, D501) ),
       ((3.61, MaxVer),  L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
87:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
88:  ( (None,            L001, A010, (A100, D102), (A200, D201, D102), (A300, D300), (A400, D102), (A500, D501) ), ),
95:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
96:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
97:  ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), None,         (A500, D501) ), ),
98:  ( (None,            L002, A011, (A100, D150), (A200, D201, D150), None,         (A400, D450), (A500, D551) ), ),
100: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
105: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
106: ( (None,            L001, A010, (A100, D103), (A200, D201, D103), (A300, D300), (A400, D403), (A500, D501) ), ),
112: ( (None,            L001, A010, (A100, D152), (A200, D201, D152), (A300, D300), None,         (A500, D501) ), )
}
'''

# ====================================================================

# Now some practical implementations
	 	 
	
class SerialLink(P000):
	"""
		A serial link will look something like this, though real
		implementations will probably override most of it.
	"""
	
	def __init__(self, device, timeout = 5):
		self.timeout = timeout
		self.ser = serial.Serial(device, timeout=self.timeout, baudrate=9600)

	def initserial(self):
		"Set up baud rate, handshaking, etc"
		pass

	def read(self, n):
		"""
			Read n bytes and return them. Real implementations should
			raise a LinkException if there is a timeout > self.timeout
		"""
		return self.ser.read(n)

	def write(self, data):
		self.ser.write(data)

	def settimeout(self, secs):
		self.timeout = secs

	def __del__(self):
		"""Should close down any opened resources"""
		self.close()
		
	def close(self):
		"""Close the serial port"""
		if "ser" in self.__dict__:
			self.ser.close()
	
class Garmin:
	"""
	A representation of the GPS device, which is connected
	via some physical connection, typically a SerialLink of some sort.
	"""
 
	def __init__(self, physicalLayer):
		
		self.link = L000(physicalLayer)      # at least initially
		(self.prod_id, self.soft_ver,self.prod_descs) = A000(self.link).getProductData()

		if debug > 1: print "Get supported protocols"
		
		# Wait for the unit to announce its capabilities using A001.  If
		# that doesn't happen, try reading the protocols supported by the
		# unit from the Big Table.

		physicalLayer.settimeout(2)
		
		try:
			protocol = A001(self.link)
			self.protocols = protocol.getProtocols()
			self.protos , self.protocols_unknown = protocol.FormatA001()
		
		except LinkException, e:
		
			if debug > 2: print "PCP not supported"
			
			try:
				self.protocols = protocol.getProtocolsNoPCP(self.prod_id, self.soft_ver)
				self.protos , self.protocols_unknown = protocol.FormatA001()
				#protos = GetProtocols(self.prod_id, self.soft_ver)
			except KeyError:
				raise Exception, "Couldn't determine product capabilities"	
				
		physicalLayer.settimeout(5)
			
		'''
		# Testing software for not PCP gps.
		
		print "Simulate a GPS"
		self.prod_id = 29
		self.soft_ver = 6.1
		self.prod_descs = ['Test Gps']
		self.link = L000(physicalLayer)
		protocol = A001(self.link)
		self.protocols = protocol.getProtocolsNoPCP(self.prod_id,self.soft_ver)
		self.protos , self.protocols_unknown = protocol.FormatA001()
		print self.protocols
		print self.protos
		print "End simulation"
		print
		'''
		
		""" Old Code
		
		# Examples :
		# self.linkProto = __main__.L001
		# wptProtos = [<class __main__.A100 >, <class __main__.D109>]
		# rteProtos = [<class __main__.A201 >, <class __main__.D202>, <class __main__.D109 >, <class __main__.D210 >]
		# trkProtos = [<class __main__.A301 >, <class __main__.D310 >, <class __main__.D301>]
			
		(versions, self.linkProto, self.cmdProto, wptProtos, rteProtos,
		 trkProtos, prxProtos, almProtos) = protos
		
		self.link = self.linkProto(physicalLayer)
		
		# The datatypes we expect to receive

		self.wptType = wptProtos[1]
		self.rteTypes = rteProtos[1:]
		self.trkTypes = trkProtos[1:]
		
		# Now we set up 'links' through which we can get data of the
		# appropriate types
		
		# ex. self.commando = TransferProtocol(A010,L001)
		# This is for sending simple commando's 
		# Like aborting the transfer, turn gps out, ..
		
		self.command = TransferProtocol(self.link, self.cmdProto)
		
		# ex. self.wptLink = A100(L001,A010,D109)
		
		self.wptLink = wptProtos[0](self.link, self.cmdProto, self.wptType)
		
		# ex. self.rteLink = A201(LOO1,AO10,(D202,D109,D210)
		self.rteLink = rteProtos[0](self.link, self.cmdProto, self.rteTypes)
		
		# ex; self.trkLink = A301(LOO1,AO10,(D310,D301))
		self.trkLink = trkProtos[0](self.link, self.cmdProto, self.trkTypes)
		
		# ex. self.prxLink = A400(LOO1,A010,D109)
		
		if prxProtos != None:
			self.prxType = prxProtos[1]
			self.prxLink = prxProtos[0](self.link, self.cmdProto, self.prxType)

		# ex self.almLink = A500(LOO1,A010,D501)
		
		if almProtos != None:
			self.almType = almProtos[1]
			self.almLink = almProtos[0](self.link, self.cmdProto, self.almType)
			
		self.timeLink = A600(self.link, self.cmdProto, D600)
		self.pvtLink  = A800(self.link, self.cmdProto, D800)
	"""
	
		# Ok now init
		"""  Protos could look like this :
		protos = {'phys': ['P000'], 'data_time': ['A600', 'D600'], 'track': ['A301', 'D310', 'D301'], 
		'route': ['A201', 'D202', 'D109', 'D210'], 'link': ['L001'], 
		'waypoint': ['A100', 'D109'], 'almanac': ['A500', 'D501'], 'position': ['A700', 'D700'], 
		'command': ['A010'], 'proximity': ['A400', 'D109'], 'pvt': ['A800', 'D800']}
		"""
	
		self.link = self.protos["link"][0](physicalLayer)
		self.cmdProto = self.protos["command"][0]
		
		# Now we set up 'links' through which we can get data of the
		# appropriate types
		
		# ex. self.commando = TransferProtocol(A010,L001)
		# This is for sending simple commando's 
		# Like aborting the transfer, turn gps out, ..		
		
		self.command = TransferProtocol(self.link, self.cmdProto )
		
		# ex. self.wptLink = A100(L001,A010,D109)
		if self.protos.has_key("waypoint"):
			self.wptLink = self.protos["waypoint"][0](self.link, self.cmdProto,self.protos["waypoint"][1])
		
		# ex. self.rteLink = A201(LOO1,AO10,(D202,D109,D210)
		if self.protos.has_key("route"):
			self.rteLink = self.protos["route"][0](self.link, self.cmdProto,self.protos["route"][1:])
		
		# ex. self.trkLink = A301(LOO1,AO10,(D310,D301))
		if self.protos.has_key("track"):
			self.trkLink = self.protos["track"][0](self.link, self.cmdProto,self.protos["track"][1:])
			
		# ex. self.prxLink = A400(LOO1,A010,D109)
		if self.protos.has_key("proximity"):
			self.prxLink = self.protos["proximity"][0](self.link, self.cmdProto,self.protos["proximity"][1])
		
		# self.timeLink = A500(L001,A010,D501) 
		if self.protos.has_key("almanac"):
			self.almLink = self.protos["almanac"][0](self.link, self.cmdProto,self.protos["almanac"][1])
		
		# self.timeLink = A600(LOO1,A010,D600)
		if self.protos.has_key("data_time"):
			self.timeLink = self.protos["data_time"][0](self.link, self.cmdProto,self.protos["data_time"][1])
			
		# self.flightBook = A650(L001,A010,D650)
		if self.protos.has_key("flightbook"):
			self.flightBook = self.protos["flightbook"][0](self.link, self.cmdProto,self.protos["flightbook"][1])
			
		# Sorry, no link for A700
		
		# self.pvtLink = A800(self.link, self.cmdProto, D800)	
		if self.protos.has_key("pvt"):
			self.pvtLink  = self.protos["pvt"][0](self.link, self.cmdProto,self.protos["pvt"][1])
			
		# self lapLink = A906(self.link, self.cmdProto,D906)
		if self.protos.has_key("lap"):
			self.lapLink = self.protos["lap"][0](self.link, self.cmdProto,self.protos["lap"][1])
			
	def getWaypoints(self,callback = None):
		return self.wptLink.getData(callback)
	
	def putWaypoints(self,data,callback = None):		
		return self.wptLink.putData(data,callback)
		
	def getRoutes(self,callback = None):
		return self.rteLink.getData(callback)
		
	def putRoutes(self,data,callback = None):
		return self.rteLink.putData(data,callback)
		
	def getTracks(self,callback = None):
		return self.trkLink.getData(callback)
		
	def putTracks(self,data,callback = None):
		return self.trkLink.putData(data,callback)
		
	def getProxPoints(self, callback = None):
		return self.prxLink.getData(callback)
		
	def putProxPoints(self,data,callback = None):
		return self.prxLink.putData(data,callback)
		
	def getAlmanac(self,callback = None):
		return self.almLink.getData(callback)
		
	def getTime(self,callback = None):
		return self.timeLink.getData(callback)

	def getFlightBook(self,callback = None):
		return self.flightBook.getData(callback)		
			
	def pvtOn(self):
		return self.pvtLink.dataOn()

	def pvtOff(self):
		return self.pvtLink.dataOff()
		
	def getPvt(self,callback = None):
		return self.pvtLink.getData(callback)
		
	def getLaps(self,callback = None):
		return self.lapLink.getData(callback)
		
	def abortTransfer(self):
		return self.command.abortTransfer()
		
	def turnPowerOff(self):
		return self.command.turnPowerOff()

# Callback examples functions

def MyCallbackgetWaypoints(waypoint,recordnumber,totalWaypointsToGet,tp):
	# We get a tuple back (waypoint,recordnumber,totalWaypointsToGet)
	# tp is the commando to send/get from the gps, look at the docs (Garmin GPS Interface Specification)
	# pag 9,10 or 4.2 L001 and L002 link Protocol	
	
	print "---  waypoint ", " %s / %s " % (recordnumber,totalWaypointsToGet), "---" 

	print "str output --> ",waypoint # or repr(waypoint)
	print 
	
	if recordnumber != totalWaypointsToGet:
		print "directory output : --> ", waypoint.getDict() # or waypoint.dataDict
	else:
		print
		print "This is the last waypoint :"
		print
		
		for x in waypoint.dataDict:
			print x, " --> ",waypoint.dataDict[x]
		
	print "Commando :",tp
	print 
	
def MyCallbackputWaypoints(waypoint,recordnumber,totalWaypointsToSend,tp):
	# we get a tuple waypoint,recordnumber,totalWaypointsToSend,tp

	print "waypoint %s added to gps (total waypoint(s) : %s/%s) waypoint command : %s" % (waypoint.dataDict['ident'],recordnumber,totalWaypointsToSend,tp)
	
def MyCallbackgetRoutes(point,recordnumber,totalpointsToGet,tp):

	#print point.__class__
	
	if isinstance(point,(RouteHdr)):
		print "Route : ", point
		
	# I really don't want the D210_Rte_Link_Type
	
	elif not isinstance(point,RouteLink):
	
		if recordnumber != totalpointsToGet:
			print "   ", point
		else:
			print
			print "This is the last waypoint of a route:"
		
			for x in point.dataDict: # or point.getDict()
				print x, " --> ",point.dataDict[x]
				
def MyCallbackputRoutes(point,recordnumber,totalPointsToSend,tp):

	if isinstance(point,RouteHdr):
		print
		print "Adding route :",point
	elif not isinstance(point,RouteLink):
		print "   waypoint added",point.dataDict['ident']
		
				
def MyCallbackgetTracks(point,recordnumber,totalPointsToGet,tp):
	
	if isinstance(point,TrackHdr):
		print "Track :",point
	else:
		
		if recordnumber != totalPointsToGet:
		
			print "   ",point,
			
			if point.dataDict['new_trk'] == True:
				print "(New track segment)",
				
			print 
			
		else:
			print
			print "This is the last waypoint of a track:"
		
			for x in point.dataDict:
				print x, " --> ",point.dataDict[x]
				
			print "Time are the seconds since midnight 31/12/89 and are only correct for the ACTIVE LOG !! (hmmm...)"
			
def MyCallbackputTracks(point,recordnumber,totalPointsToSend,tp):

	if isinstance(point,TrackHdr):
		print "Track :", point
	else:
		print "   ", point.dataDict
		
def MyCallbackgetAlmanac(satellite,recordnumber,totalPointsToGet,tp):

	print 
	
	for x in satellite.dataDict:
		print "%7s --> %s" % (x,satellite.dataDict[x])
		
	
def main():

	if os.name == 'nt':
		#0 is com1, 1 is com2 etc
		serialDevice =  0
	else:
		serialDevice =  "/dev/ttyS0"
		
		if sys.platform[:-1] == "freebsd":
			serialDevice =  "/dev/cuaa0" # For FreeBsd
			
	phys = SerialLink(serialDevice)
	
	gps = Garmin(phys)
	
	print "GPS Product ID: %d Descriptions: %s Software version: %2.2f" % \
				 (gps.prod_id, gps.prod_descs, gps.soft_ver)
	print
				 
	# Show gps information
	
	if 1:
		print
		print "GPS Product ID :",gps.prod_id
		print "GPS version    :",gps.soft_ver
		print "GPS            :",gps.prod_descs[0]
		print "MapSource info :",gps.prod_descs[1:]
		print 
		print "Product protocols:"
		print "------------------"
		
		# Some code from pygarmin, small but smart
		
		for i in range(len(gps.protocols)):
			p = gps.protocols[i]
			
			if  p[0] == 'D':
				print p,
			else:
				if i == 0:
					print p,
				else:
					print 
					print p,
					
		print 
		
		# print unknown protocols
		
		if len(gps.protocols_unknown):
			print
			print "Product protocols who are not supported yet:"
			print "--------------------------------------------"
			
			for i in range(len(gps.protocols_unknown)):
				p = gps.protocols_unknown[i]
			
				if  p[0] == 'D':
					print p,
				else:
					if i == 0:
						print p,
					else:
						print 
						print p,
						
			print
			
	# Show waypoints
	
	if 0:
		
		# First method, just get the waypoints in a list (look at class A100, function __str__)
		
		waypoints = gps.getWaypoints()
	
		print "Waypoints :"
		print "-----------"
		
		for x in waypoints:
			print x 
			
		print	
		print	"Same waypoints called by a callback function:"
		print "---------------------------------------------"
		print
		
		# Same but now with a Callback function
		# Everytime we get a waypoint from the gps the function MyCallbackWaypoints is called
			
		gps.getWaypoints(MyCallbackgetWaypoints) 
		
		# or waypoints = gps.getWaypoints(MyCallbackgetWaypoints)
		
	# Send waypoints

	if 0:			
		data1 = {}
		data1['ident'] = "01TEST"
		data1['cmnt'] = "A TEST POINT"
		data1['slat'] = 624447295
		data1['slon'] = -2529985
	
		data2 = {}
		data2['ident'] = "02TEST"
		data2['cmnt'] ="A TEST POINT"
		data2['slat'] = 624447295
		data2['slon']= -2529985

		data3 = {'ident':"CLUB91",'cmnt':"DRINKING",'slat':606532864,'slon':57654672,'smbl':13}
	
		print "Send waypoints to gps :"
		print "----------------------"
		
		gps.putWaypoints([data1,data2,data3],MyCallbackputWaypoints)
		
		# or gps.putWaypoints([data1,data2]) without a callback function
		
		print
		print "Are there 3 waypoints added to your gps ??"
			

	# Show Routes
	
	if 0:
		
		routes = gps.getRoutes()
		
		print "Routes"
		print "------"
		
		for route in routes:
			print
			print "Route name :", route[0]
			
			for point in route[1:]:
			
				# Ok, Bad way to remove D210_Rte_Link_Type entrys
				
				if len(point) > 23:
					print "   ",point
					
		# Now with a callback function
		
		print
		print "Same routes but now with a callback function :"
		print "---------------------------------------------"
		print
		
		gps.getRoutes(MyCallbackgetRoutes)
		
	# Put Routes
		
	if 0:
	
		# Test Route 1
		
		header1 = {'nmbr':1,'ident':"DRINKING"}
			
		data1_1 = {}
		data1_1['ident'] = "SOCCER"
		data1_1['cmnt'] = "MY SOCCER"
		data1_1['slat'] = 606476436
		data1_1['slon'] = 57972861
	
		data2_1 = {}
		data2_1['ident'] = "CLUB91"
		data2_1['cmnt'] = "DRINKING"
		data2_1['slat'] = 606532864
		data2_1['slon'] = 57654672
	
		# Test Route 2
			
		header2 = {'nmbr':2,'ident':"TEST ROUTE 2"}
		
		data1_2 = {}
		data1_2['ident'] = "TEST01"
		data1_2['slat'] = 608466698
		data1_2['slon'] = 46580036
		
		data2_2 = {'ident': "TEST02",'slat': 608479774,'slon':46650547}
		data3_2 = {'ident': "TEST03",'slat': 608451909,'slon':46665535}
		data4_2 = {'ident': "TEST04",'slat': 608440119,'slon':46644415}
		
		print "Send two routes to the gps"
		gps.putRoutes([(header1,data1_1,data2_1),(header2,data1_2,data2_2,data3_2,data4_2)])
		print "Routes added"
		
		# Now with a callback function
		
		print
		print "Same routes but now with a callback function :"
		print "---------------------------------------------"
		print "If you leave the header empty, the computer will generate one for you (ROUTE1,ROUTE2,....)"
		
		header1 = header2 = {}
		
		gps.putRoutes([(header1,data1_1,data2_1),(header2,data1_2,data2_2,data3_2,data4_2)],MyCallbackputRoutes)
		
		print
		print "Four routes are added to your gps, two of them are generated !"
		print "and a few waypoints"
		
	# Show Tracks
	
	if 0:
		print "Tracks"
		print "------"
		
		tracks = gps.getTracks()
		
		for track in tracks:
		
			# Check for multiple tracks
			
			if type(track) == list:
				print
				print "Track name :",track[0]
		
				for point in track[1:]:
					print "   ",point
			else:
				print track
		
		# Now with a callback function
		
		print
		print "Same tracks but now with a callback function :"
		print "---------------------------------------------"
	
		gps.getTracks(MyCallbackgetTracks)
		
	# Send tracks
	
	if 0:
		print "Sending tracks with a callback function :"
		print "-----------------------------------------"
		print "If you leave the header empty, the computer will generate one for you (TRACK1,TRACK2,....)"
		print "It's possible to send track to the ACTIVE LOG.but you can't send time to tracks"
		
		
		header1 = {'ident':'TEST TRACK'}
		#header1 = {'ident':'ACTIVE LOG'}  # for sending track's to the ACTIVE LOG
		data1_1 = {'slat': 608528384,'slon': 46271488}
		data2_1 = {'slat': 608531200,'slon': 46260224}
		data3_1 = {'slat': 608529664, 'slon': 46262272}
		
		header2 = {}
		data1_2 = {'slat': 608529718,'slon': 46262291}
		data2_2 = {'slat': 608529718,'slon': 46262291}
		data3_2 = {'slat': 608532699,'slon': 46250150, 'new_trk': True}
		data4_2 = {'slat': 608526491,'slon': 46257149}
		data5_2 = {'slat': 608520439,'slon': 46264816}
		data6_2 = {'slat': 608521779,'slon': 46262842}
		
		# Check if we can store multiple tracklogs
		
		if isinstance(gps.trkLink,A300):
			gps.putTracks([(data1_1,data2_1,data3_1),
										 (data1_2,data2_2,data3_2,data4_2,data5_2,data6_2)],MyCallbackputTracks)
										 
			print "Track added ?"
			
		else:
			gps.putTracks([(header1,data1_1,data2_1,data3_1),
										 (header2,data1_2,data2_2,data3_2,
										  data4_2,data5_2,data6_2)],MyCallbackputTracks)
										
			print "Two track logs added ?"
		
	# Show proximity points

	if 0:
		print "Proximity waypoints:"
		print "-------------------"
		
		for proxi in gps.getProxPoints():
			print proxi
	
	# Send	proximity points
	
	if 0:
		print "Sending 2 proximity waypoints :"
		print "-------------------------------"
		
		data1 = {'ident':'WATER','slat': 608688816,'slon': 45891108,'dist':300}
		data2 = {'ident':'AERPRT','slat': 607132209,'slon': 53673984,'dist':400}
		gps.putProxPoints([data1,data2])
		
		print "Check your waypoint and proximity waypoint menu on your gps!"
		
	# Show almanac
	
	if 0:
		print "Almanac information:"
		print "--------------------"
		
		gps.getAlmanac(MyCallbackgetAlmanac)
		
	# Show FlightBook
	
	if 0:
		print "FlightBook information:"
		print "-----------------------"
		
		flightbook = gps.getFlightBook()
		
		for x in flightbook:
			print x 		

	# Show date and time
		
	if 0:
		print "Date and time:"
		print "--------------"
		
		def MyCallbackgetTime(timeInfo,recordnumber,totalPointsToGet,tp):
			print timeInfo.getDict() # or timeInfo.dataDict
			
		print gps.getTime(MyCallbackgetTime)
		
	# Show some real-time data
	
	if 0:
		print "Starting pvt"
		print "-----------"
		
		gps.pvtOn()
		
		def MyCallbackgetPvt(pvt,recordnumber,totalPointsToGet,tp):
			print pvt.getDict()
			
		try:
			for i in range(10):
				p = gps.getPvt(MyCallbackgetPvt)
				print p
				
		finally:
			print "Stopping pvt"
			gps.pvtOff()
		
	# Show Lap type info
	
	if 0:
		print "Lap info"
		print "--------"
		
		laps = gps.getLaps()
		
		for x in laps:
			print x 		
		
if __name__ == "__main__":
	main()
