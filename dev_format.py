#!/usr/bin/env python

import garmin,datetime,os,sys

""" Introduction
version : 0.1
date : 21-jul-04

Get info from the GPS and save it into OziExplorer format
Send a OziExplorer file to the gps

Todo : 
 - point.dataDict['alt'], little round problem
 - of course bugs
 - volunteers for the Fuwawi format ?
 - other formats ?
"""

debug = True

def degrees(semi):
	return semi * 180.0 / (1L<<31)
	
def semi(deg):
	return long(deg * ((1L<<31) / 180))
	
class OziExplorer:

	# Tried to map ozie symbols, probably forgot some and some are wrong, why make things different for some gps ???
	
	gps2ozie = {0:35,1:72,2:84,2:84,3:109,4:79,5:80,
							6:2,7:23,8:25,9:88,10:46,11:47,12:86,
							13:3,14:112,15:85,16:110,17:114,18:70,19:54,21:34,
							22:92,23:93,24:94,25:95,26:96,27:97,28:98,
							29:99,30:100,31:101,32:102,33:103,34:104,36:115,
							37:108,150:5,151:8,152:48,153:57,154:21,155:63,
							156:36,157:32,158:42,159:41,160:43,161:51,162:58,
							163:61,164:19,165:77,166:20,167:111,169:1,170:9,
							171:31,172:55,173:30,174:38,175:66,176:67,178:83,
							179:75,8195:89,8197:28,8198:15,8199:14,8200:13,8203:76,8204:71,
							8205:73,8206:74,8207:10,8208:22,8209:82,8210:90,8211:91,
							8212:106,8213:107,8214:44,8215:49,8216:52,8217:113,8218:78,
							8219:116,8220:17,8221:87,8226:50,8227:64,8233:6,8234:7,
							8235:11,8236:12,8237:16,8238:18,8239:26,8240:33,8241:37,
							8242:39,8243:68,8244:4,8245:24,8246:60,8249:151,8251:152,
							8252:153,8253:154,8255:117,8256:118,16384:0,16388:29,16389:45,
							16390:59,16391:62,16392:56,16393:27,16394:69,16395:40,16402:53}

	ozie2gps = {0:16384,1:169,2:6,3:13,4:8244,5:150,6:8233,
							7:8234,8:151,9:170,10:8207,11:8235,12:8236,13:8200,
							14:8199,15:8198,16:8237,17:8220,18:8238,19:164,20:166,21:154,
							22:8208,23:7,24:8245,25:8,26:8239,27:16393,28:8197,
							29:16388,30:173,31:171,32:157,33:8240,34:21,35:0,
							36:156,37:8241,38:174,39:8242,40:16395,41:159,42:158,
							43:160,44:8214,45:16389,46:10,47:11,48:152,49:8215,
							50:8226,51:161,52:8216,53:16402,54:19,55:172,56:16392,
							57:153,58:162,59:16390,60:8246,61:163,62:16391,63:155,
							64:8227,66:175,67:176,68:8243,69:16394,70:18,71:8204,72:1,
							73:8205,74:8206,75:179,76:8203,77:165,78:8218,79:4,
							80:5,82:8209,83:178,84:2,84:2,85:15,86:12,
							87:8221,88:9,89:8195,90:8210,91:8211,92:22,93:23,
							94:24,95:25,96:26,97:27,98:28,99:29,100:30,
							101:31,102:32,103:33,104:34,106:8212,107:8213,108:37,
							109:3,110:16,111:167,112:14,113:8217,114:17,115:36,
							116:8219,117:8255,118:8256,151:8249,152:8251,153:8252,154:8253}

	def __init__(self,gps):
		self.gps = gps
		
	def delphiTimeNow(self):
		inittime = datetime.datetime(1899, 12, 30)
		timenow = datetime.datetime.now()
		timedifference = timenow - inittime
		return timedifference.days + timedifference.seconds / 86400.0			
		
	def getWaypointsFromGps(self,waypoint,recordnumber,totalWaypointsToGet,tp):
		data = ['' for x in range(24)]

		data[0] = recordnumber
		data[1] = waypoint.dataDict['ident']
		data[2] = round(degrees(waypoint.dataDict['slat']),5)
		data[3] = round(degrees(waypoint.dataDict['slon']),5)
		data[4] = self.delphiTimeNow()
		
		# Can our gps handle symbols ?
			
		if waypoint.dataDict.has_key('smbl'):
			
			if self.gps2ozie.has_key(waypoint.dataDict['smbl']):
				data[5] = self.gps2ozie[waypoint.dataDict['smbl']]
			else:
				data[5] = 18 # standard waypoint symbol
			
		data[6] = 1 
		data[7] = 4
		data[8] = 0
		data[9] = 65535
		data[10] = waypoint.dataDict['cmnt']
		data[11] =0
		data[12] = 0
		data[13] = 0
		data[14] = -777
		
		if waypoint.dataDict.has_key('alt'):
			data[14] = int(round(waypoint.dataDict['alt'] * 3.280,0))  # feet = Meters * 3.280
			
		data[15] = 6
		data[16] = 0
		data[17] = 17
		data[18] = 0
		data[19] = 10.0
		data[20] = 2
		
		#print recordnumber, waypoint.dataDict['ident'],waypoint.dataDict['smbl'],waypoint.dataDict['wpt_class']
		print >> self.file, '%4s,%s,%11.6f,%11.6f,%13.7f,%3s,%2s,%2s,%10s,%10s,%s,%2s,%2s,%5s,%7s,%2s,%2s,%s,%s,%s,%s,%s,%s,%s' % tuple(data)	
	
	def getWaypoints(self,file):
	
		self.file = open(file,"w")
		
		print >> self.file, "OziExplorer Waypoint File Version 1.1"
		print >> self.file, "WGS 84"
		print >> self.file, "Reserved 2"
		print >> self.file, "garmin"
		
		self.gps.getWaypoints(self.getWaypointsFromGps)
		
		self.file.close()

	def getRoutesFromGps(self,point,recordnumber,totalpointsToGet,tp):
		
		#print point.__class__, which routeheader
	  
		if isinstance(point,(garmin.D200)):
			self.routedata.append(['R',0,point.dataDict['nmbr'],'',0])
		elif isinstance(point,(garmin.D201)):
			self.routedata.append(['R',0,point.dataDict['nmbr'],self.dataDict['cmnt'],0])
		elif isinstance(point,(garmin.D202)):
			self.routedata.append(['R',0,point.dataDict['ident'],'',0])
		
		# I really don't want the D210_Rte_Link_Type
	
		elif not isinstance(point,garmin.RouteLink):
			data = [0 for x in range(16)]
		
			data[0] = 'W'
			data[4] = point.dataDict['ident']
			data[5] = round(degrees(point.dataDict['slat']),5)
			data[6] = round(degrees(point.dataDict['slon']),5)
			data[7] = self.delphiTimeNow()
			
			# Can our gps handle symbols ?
			
			if point.dataDict.has_key('smbl'):
			
				if self.gps2ozie.has_key(point.dataDict['smbl']):
					data[8] = self.gps2ozie[point.dataDict['smbl']]
				else:
					data[8] = 18 # standard waypoint symbol
			
			data[9] = 1
			data[10] = 4
			data[12] = 65535
			data[13] = point.dataDict['cmnt']
						
			self.routedata.append(data)
					
	def getRoutes(self,file):
		self.file = open(file,"w")
	
		print >> self.file, "OziExplorer Route File Version 1.0"
		print >> self.file, "WGS 84"
		print >> self.file, "Reserved 1"
		print >> self.file, "Reserved 2"
	
		self.routedata = []
		self.gps.getRoutes(self.getRoutesFromGps)
		
		routenr = -1
		color = {0:255,1:16711680,2:65280,3:32768,4:16711935,5:0,6:8388736}
		waypointdata = {}
		wpLowrances = 0
		
		for point in self.routedata:	
			
			# check if route
			
			if point[0] == 'R':
				routenr += 1
				waypointnr = 0
				point[1] = routenr
				point[4] = color[routenr % 7]
				print >> self.file, "%s,%3s,%-16s,%s,%s" % tuple(point)
			else:
				# it's a waypoint
				
				waypointnr += 1
				point[1] = routenr
				point[2] = waypointnr
				
				if waypointdata.has_key(point[4]):
					point[3] = waypointdata[point[4]]
				else:
					wpLowrances += 1
					waypointdata[point[4]] = wpLowrances
					point[3] = wpLowrances
					
				print >> self.file, "%s,%3s,%3s,%3s,%-16s,%11.6f,%11.6f,%s,%s,%2s,%2s,%10s,%10s,%s,%2s,%2s" % tuple(point)
				
		for x in range(routenr,101):
			print >> self.file,"%s,%3s,R%-16s,%s,%s" % ("R",x,x,"",color[x % 7])
							
		self.file.close()
		
	def getTracksFromGps(self,point,recordnumber,totalPointsToGet,tp):
		#print point.__class__
		
		if isinstance(point,(garmin.D310)):
			self.trackheader[point.dataDict['ident']] = (0,2,255,point.dataDict['ident'],0,0,2,8421376)
			self.header = point.dataDict['ident']
			self.trackdata[self.header] = []
		else:
			data = [ '' for x in range(7) ]
			data[0] = round(degrees(point.dataDict['slat']),5)
			data[1] = round(degrees(point.dataDict['slon']),5)
			data[2] = point.dataDict['new_trk']
			data[3] = -777
			# inittime = datetime.datetime(1899, 12, 30)
			# timenow = datetime.datetime(1989,12,31)
			# timedifference = timenow - inittime
			# timedifference.days --> 32873
			# datetime.datetime(1989,12,31)
			data[4] = round((point.dataDict['time'] + 86400 * 32873) / 86400.0,7)
			delphitime = datetime.datetime(1989,12,31)  + datetime.timedelta(seconds=point.dataDict['time'])
			data[5] = delphitime.strftime("%d-%b-%y")
			data[6] = delphitime.strftime("%H:%M:%S")
			
			# if the time = 31-Dec-89,00:00:00
			# This happens when we saved a track to the ACTIVE LOG and then get it back

			if data[4] == 32873:
				data[4] = 0.0
				data[5] = data[6] = "   "
		
			if isinstance(point,(garmin.D301)):
				data[3] = round(point.dataDict['alt'] * 3.280,1)  # feet = Meters * 3.280
				
				# if track isn't the ACTIVE LOG discard the time (wrong results)
				
				if self.header != "ACTIVE LOG":
					data[4] = 0.0
					data[5] = data[6] = "   "
					
				self.trackdata[self.header].append(data)
			else:
				self.trackdata['ACTIVE LOG'].append(data)
			
	def getTracks(self,path = os.getcwd()):
		self.trackheader = {'ACTIVE LOG' : []}
		self.trackdata = {}
			
		self.gps.getTracks(self.getTracksFromGps)
			
		for trackroute in self.trackheader.keys():
			self.file = open(path + "/" + trackroute + ".plt","w")
			print >> self.file, "OziExplorer Track Point File Version 2.1"
			print >> self.file, "WGS84"
			print >> self.file, "Altitude is in Feet"
			print >> self.file, "Reserved 3"				
			print >> self.file, "%s,%s,%s,%-35s,%s,%s,%s,%s" % tuple(self.trackheader[trackroute])
			print >> self.file, len(self.trackdata[trackroute])
				
			for waypoint in self.trackdata[trackroute]:
				print >> self.file, "%11.6f,%11.6f,%s,%7.1f,%13.7f,%s,%s" % tuple(waypoint)
				
		self.file.close()
	
	def putWaypoints(self,file):
		datafile = open(file).readlines()[4:]
		waypoints = []
		
		for record in datafile:
			waypoint = record.split(',')
			
			symbol = 18
			
			# Try to get symbol ?
			
			try:
				symbol = self.ozie2gps[int(waypoint[5])]
				
			except ValueError,KeyError:
				pass
					
			data = {'ident':waypoint[1].strip(),
							'slat':semi(float(waypoint[2])),
							'slon':semi(float(waypoint[3])),
							'smbl':symbol,
							'cmnt': waypoint[10].strip(),
							'alt':float(waypoint[14]) / 3.280}
										
			waypoints.append(data)
	
		if debug:
			print "Send waypoints to gps :"
			print "----------------------"
			
			for x in waypoints:
				print x
		
		self.gps.putWaypoints(waypoints)
		
	def putRoutes(self,file):
		datafile = open(file).readlines()[4:]
	
		# check where the last waypoint in the file is
		
		for last in range(len(datafile) - 1,-2,-1):
		
			if datafile[last][0] == 'W':
				break
		
		routes = []
		routenr = -1
				
		for record in datafile[:last + 1]:
			
			point = record.split(',')
			
			if point[0] == "R":
				routenr +=  1
				routes.append([{'ident': point[2].strip()}])
			else:
			
				symbol = 18
			
				# Try to get symbol ?
			
				try:
					symbol = self.ozie2gps[int(point[8])]
				except ValueError,KeyError:
					pass
			
				data = {'ident':point[4].strip(),
								'slat':semi(float(point[5])),
								'slon':semi(float(point[6])),
								'smbl':symbol,
								'cmnt': point[13].strip()}
				
				routes[routenr].append(data)
				
		if debug:
			print "send routes to gps :"
			print "--------------------"
			
			for route in routes:
				print route[0]
				
				for waypoint in route[1:]:
					print "   ", waypoint
					
				print
				
		self.gps.putRoutes(routes)
		
	def putTracks(self,file):
		datafile = open(file).readlines()[4:]
	
		track = []
		
		# Check if gps can store multiple tracks 
		
		print self.gps.trkLink.__class__
		
		if not isinstance(self.gps.trkLink,garmin.A300):
			header = datafile[0].split(',')[3]
			header = {'ident':datafile[0].split(',')[3].strip()} # split the first line and strip the 3 postion (=track header)
			track.append(header)
			
		for record in datafile[2:]:
			waypoint = record.split(',')
			
			# Convert Delphi format to gps format and maybe one day you can send time values to the gps
			
			delphitime = float(waypoint[4])
			delphidate = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=int(delphitime),seconds = round((delphitime - int(delphitime)) * 86400)) 
			gpsdate = datetime.datetime(1989,12,31)
			diftime = delphidate - gpsdate
			
			data = {'slat':semi(float(waypoint[0])),
							'slon':semi(float(waypoint[1])),
							'new_trk':int(waypoint[2]),
							# 'time':diftime.days * 86400 + diftime.seconds,
							'alt':float(waypoint[3]) / 3.280}
							
			track.append(data)
			
		if debug:
			print "send tracks to gps :"
			print "--------------------"
			
			for point in track:
				print point
		
		self.gps.putTracks([track])
		
def main():

	if os.name == 'nt':
		serialDevice =  0
		phys = Win32SerialLink(serialDevice)
	else:
		serialDevice =  "/dev/ttyS0"
		
		if sys.platform[:-1] == "freebsd":
			serialDevice =  "/dev/cuaa0" # For FreeBsd

	phys = garmin.SerialLink(serialDevice)
	
	# Don't forget to convert between different OS
	# Windows text files record separator : \r\n
	# Unix text files record separator \n
	# Use the right tools to convert them
	
	# nawk 'BEGIN {RS = "\r\n";ORS = "" } {print $0}' oziewayp1.wpt  > oziewayp1.stripped.wpt
	
	gps = garmin.Garmin(phys)
	gps.wptLink.abortTransfer()
	ozie = OziExplorer(gps)
	
	print "Check the code:"
	print "---------------"
	print "Get the waypoint(s) and save them to the file: ozie.wpt"
	ozie.getWaypoints("ozie.wpt")
	print "Get the route(s) and save them to the file: ozie.rte"
	ozie.getRoutes("ozie.rte")
	print "Get the track(s) and save them to *.plt files"
	ozie.getTracks()
	
	#ozie.putWaypoints("/path/to/ozie.wpt")
	#ozie.putRoutes("/path/to/ozie.rte")
	#ozie.putTracks("/path/to/ozie.plt")
	
if __name__ == "__main__":
	main()
