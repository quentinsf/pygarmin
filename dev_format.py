#!/usr/bin/env python

import garmin,datetime,os,sys
#from xml.dom import minidom
import sys
import codecs
from xml.sax import make_parser
from xml.sax.handler import ContentHandler

"""
version : 0.2
date : 24-dec-04

Get and send info to GPX format. GPX format is a standard XML schema for gps and used with lots of other programs. (http://www.topografix.com/GPX/1/1 )


----------------------------------------------------------
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

# A simple XML-generator# Originally Lars Marius Garshol, September 1998
# http://mail.python.org/pipermail/xml-sig/1998-September/000347.html
# Changes by Uche Ogbuji April 2003
# *  unicode support: accept encoding argument and use Python codecs
#    for correct character output
# *  switch from deprecated string module to string methods
# *  use PEP 8 style
# Changes by Gerrit Sere December 2004
#               Use list instead of hashes, attributs are always printed in the order I like
#               Choose if the attribute is printed on the same line

class XMLWriter:

    def __init__(self, out=sys.stdout, encoding="utf-8", indent=u"  "):

        """
        out      - a stream for the output
        encoding - an encoding used to wrap the output for unicode
        indent   - white space used for indentation
        """

        wrapper = codecs.lookup(encoding)[3]
        self.out = wrapper(out)
        self.stack = []
        self.indent = indent
        self.out.write(u'<?xml version="1.0" encoding="%s"?>\n' % encoding)

    def doctype(self, root, pubid, sysid):

        """
        Create a document type declaration (no internal subset)
        """

        if pubid == None:
            self.out.write(u"<!DOCTYPE %s SYSTEM '%s'>\n" % (root, sysid))
        else:
            self.out.write(u"<!DOCTYPE %s PUBLIC '%s' '%s'>\n" % (root, pubid, sysid))

    #def push(self, elem, attrs={}):
    def push(self, elem, attrs=(),newline=[False,]):

        """
        Create an element which will have child elements
        """

        i=0
        total = len(attrs)

        self.__indent()
        self.out.write("<" + elem)

        for (a, v) in attrs:

            if i < total:

                try:
                    if newline[i]: self.out.write(u"\n")
                except IndexError:
                    if newline[0]: self.out.write(u"\n")

                i+=1

            self.out.write(u' %s="%s"' % (a, self.__escape_attr(str(v))))

        self.out.write(u">\n")
        self.stack.append(elem)

    def elem(self, elem, content, attrs=(),newline=[False,]):

        """
        Create an element with text content only
        """

        i=0
        total = len(attrs)

        self.__indent()
        self.out.write(u"<" + elem)

        for (a, v) in attrs:

            if i < total:

                try:
                    if newline[i]: self.out.write(u"\n")
                except IndexError:
                    if newline[0]: self.out.write(u"\n")

                i+=1

            self.out.write(u' %s="%s"' % (a, self.__escape_attr(str(v))))

        self.out.write(u">%s</%s>\n" % (self.__escape_cont(str(content)), elem))

    def empty(self, elem, attrs=(),newline=[False,]):

        """
        Create an empty element
        """

        i=0
        total = len(attrs)

        self.__indent()
        self.out.write(u"<"+elem)

        for (a,v) in attrs:

            if i < total:

                try:
                    if newline[i]: self.out.write(u"\n")
                except IndexError:
                    if newline[0]: self.out.write(u"\n")

                i+=1

            self.out.write(u' %s="%s"' % (a, self.__escape_attr(str(v))))

        self.out.write(u"/>\n")

    def pop(self):

        """
        Close an element started with the push() method
        """
        elem=self.stack[-1]
        del self.stack[-1]
        self.__indent()
        self.out.write(u"</%s>\n" % elem)

    def content(self, content):

        """
        Create simple text content as part of a mixed content element
        """

        self.out.write(self.__escape_cont(content))

    def __indent(self):
        self.out.write(self.indent * (len(self.stack) * 2))

    def __escape_cont(self, text):
        return text.replace(u"&", u"&amp;").replace(u"<", u"&lt;")

    def __escape_attr(self, text):
        return text.replace(u"&", u"&amp;").replace(u"'", u"&apos;").replace(u"<", u"&lt;")

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


class GpxWaypointHandler(ContentHandler):

    def __init__(self):
        self.waypoints = []
        self.inWaypoint = self.inEle = self.inName = self.inCmt = False


    def startElement(self,name,attrs):

        if name == "wpt":
            self.inWaypoint = True

            self.data = {'slat':semi(float(attrs.get('lat',""))),'slon':semi(float(attrs.get('lon',"")))}

        if self.inWaypoint and name == "ele":
            self.inEle = True

        if self.inWaypoint and name == "name":
            self.inName = True

        if self.inWaypoint and name == "cmt":
            self.inCmt = True

    def characters(self,content):

        if self.inEle:
            self.data['alt'] = float(content)

        if self.inName:
            self.data['ident'] = str(content)

        if self.inCmt:
            self.data['cmnt'] = str(content)

    def endElement(self,name):

        if name == "cmt":
            self.inCmt = False

        if name == "name":
            self.inName = False

        if name == "ele":
            self.inEle = False

        if name == "wpt":
            self.inWaypoint = False
            self.waypoints.append(self.data)

class GpxRouteHandler(ContentHandler):

    def __init__(self):
        self.routes = []
        self.route = []
        self.inRte = self.inRteName = self.inRteNmbr = False
        self.inRept = self.inReptEle = self.inReptName = self.inReptCmt = False
        self.level = 0

    def startElement(self,name,attrs):

        if name == "rte":
            self.inRte = True
            self.route = []
            self.header = {}
            self.level = 1

        if self.level == 1 and name == "name":
            self.inRteName = True

        if self.level == 1 and name == "nmbr":
            self.inRteNmbr = True

        if name == "rtept":
            self.data = {'slat':semi(float(attrs.get('lat',""))),'slon':semi(float(attrs.get('lon',"")))}
            self.inRept = True
            self.level = 2

        if self.level == 2 and name == "ele":
            self.inReptEle = True

        if self.level == 2 and name == "name":
            self.inReptName = True

        if self.level == 2 and name == "cmt":
            self.inReptCmt = True

    def characters(self,content):

        if self.inRteName:
            self.header['ident'] = str(content)

        if self.inRteNmbr:
            self.header['nmbr'] = int(content)

        if self.inReptEle:
            self.data['alt'] = float(content)

        if self.inReptName:
            self.data['ident'] = str(content)

        if self.inReptCmt:
            self.data['cmnt'] = str(content)

    def endElement(self,name):

        if self.level == 1 and name == "name":
            self.inRteName = False

        if self.level == 1 and name == "nmbr":
            self.inRteNmbr = False

        if self.level == 2 and name == "ele":
            self.inReptEle = False

        if self.level == 2 and name == "name":
            self.inReptName = False

        if self.level == 2 and name == "cmt":
            self.inReptCmt = False

        if name == "rtept":
            self.route.append(self.data)
            self.inRept = False
            self.level = 1

        if name == "rte":
            self.route.insert(0,self.header)
            self.routes.append(self.route)
            self.inRte = False
            self.level = 0

class GpxTrackHandler(ContentHandler):

    def __init__(self):
        self.tracks = []
        self.track = []
        self.inTrk = self.inTrkName = self.intTrkNumber = False
        self.inTrkseg = self.inTrksegTrkpt = self.inTrksegEle = self.inTrksegTime = False
        self.level = 0

    def startElement(self,name,attrs):

        if name == "trk":
            self.inTrk = True
            self.track = []
            self.header = {}
            self.level = 1

        if self.level == 1 and name == "name":
            self.inTrkName = True

        """
        if self.level == 1 and name == "number":
                self.intTrkNumber = True
        """

        if name == "trkseg":
            self.data = {'new_trk': True}
            self.inTrkseg = True
            self.level = 2

        if self.level == 2 and name == "trkpt":
            self.data['slat'] = semi(float(attrs.get('lat',"")))
            self.data['slon'] = semi(float(attrs.get('lon',"")))
            self.inTrksegTrkpt = True
            self.level = 3

        if self.level == 3 and name == "ele":
            self.inTrksegEle = True

        """
        if self.level == 3 and name == "time":
                self.inTrksegTime = True
        """

    def characters(self,content):

        if self.inTrkName:
            self.header['ident'] = str(content)

        """
        # We don't use this info

        if self.intTrkNumber:

                pass

        """

        if self.inTrksegEle:
            self.data['alt'] = float(content)

        """

        # We can't send time

        if self.inTrksegTime:
                self.data['time'] = converting time to seconds

        """

    def endElement(self,name):

        if self.level == 1 and name == "name":
            self.inTrkName = False

        """
        if self.level == 1 and name == "number":
                self.intTrkNumber = False
        """
        if self.level == 3 and name == "ele":
            self.inTrksegEle = False

        """
        if self.level == 3 and name == "time":
                self.inTrksegTime = False
        """

        if name == "trkpt":
            self.track.append(self.data)
            self.data = {}
            self.inTrksegTrkpt = False
            self.level = 2

        if name == "trkseg":
            self.inTrkseg = False
            self.level = 1

        if name == "trk":
            self.track.insert(0,self.header)
            self.tracks.append(self.track)
            self.inTrk = False
            self.level = 0

class Gpx:

    def __init__(self,gps):
        self.gps = gps

    def getStart(self,out=sys.stdout):
        self.xml = XMLWriter(out,indent=" ")

        self.xml.push('gps',(("version",1.1),
                                                                                                 ("creator" ,"Pygarmin"),
                                                                                                 ("xmlns:xsi","http://www.w3.org/2001/XMLSchema-instance"),
                                                                                                 ("xmlns","http://www.topografix.com/GPX/1/1"),
                                                                                                 ("xsi:schemaLocation","http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd")),[True,])

        self.routenr = 0
        self.startRouteHeader = True
        self.tracknr = 0
        self.startTrackHeader = self.startTrackSegment =  True

    def getWaypointsFromGps(self,waypoint,recordnumber,totalWaypointsToGet,tp):
        self.xml.push("wpt",(("lat",degrees(waypoint.dataDict['slat'])),("lon",degrees(waypoint.dataDict['slon']))))
        self.xml.elem("name",waypoint.dataDict['ident'])
        self.xml.elem("ele",waypoint.dataDict['alt'])
        self.xml.elem("cmt",waypoint.dataDict['cmnt'])
        self.xml.pop()

    def getWaypoints(self):
        self.gps.getWaypoints(self.getWaypointsFromGps)

    def getRoutesFromGps(self,point,recordnumber,totalpointsToGet,tp):

        if isinstance(point,(garmin.RouteHdr)):

            # Each gps has another route header
            # D200 : nmbr
            # D201 : nmbr,cmnt
            # D202 : ident

            if self.startRouteHeader:
                self.startRouteHeader = False
                self.xml.push("rte")
            else:
                self.xml.pop()
                self.xml.push("rte")

            self.routenr += 1

            if point.dataDict.has_key('cmnt'):
                self.xml.elem("name",point.dataDict['cmnt'])
            elif point.dataDict.has_key('ident'):
                self.xml.elem("name",point.dataDict['ident'])
            else:
                self.xml.elem("name",'route' + str(self.routenr))

            if point.dataDict.has_key('nmbr'):
                self.xml.elem("nmbr",point.dataDict['nmbr'])
            else:
                self.xml.elem("nmbr",self.routenr)

        # I really don't want the D210_Rte_Link_Type

        elif not isinstance(point,garmin.RouteLink):
            self.xml.push("rtept",(("lat",degrees(point.dataDict['slat'])),("lon",degrees(point.dataDict['slon']))))
            self.xml.elem("ele",point.dataDict['alt'])
            self.xml.elem("name",point.dataDict['ident'])
            self.xml.elem("cmt",point.dataDict['cmnt'])
            self.xml.pop()

    def getRoutes(self):
        self.gps.getRoutes(self.getRoutesFromGps)

        # Is there a route ?

        if not self.startRouteHeader:
            self.xml.pop()

    def getTracksFromGps(self,point,recordnumber,totalPointsToGet,tp):
        #print recordnumber,point.dataDict

        if isinstance(point,garmin.TrackHdr):

            if self.startTrackHeader:
                self.startTrackHeader = False
                self.xml.push("trk")
            else:
                self.xml.pop()
                self.xml.pop()
                self.xml.push("trk")

            self.startTrackSegment = True
            self.tracknr += 1

            self.xml.elem("name",   point.dataDict['ident'])
            self.xml.elem("number",self.tracknr)

        else:

            if point.dataDict['new_trk'] == True:

                if self.startTrackSegment:
                    self.startTrackSegment = False
                    self.xml.push("trkseg")
                else:
                    self.xml.pop()
                    self.xml.push("trkseg")

            self.xml.push("trkpt",(("lat",degrees(point.dataDict['slat'])),("lon",degrees(point.dataDict['slon']))))

            self.xml.elem("ele",point.dataDict['alt'])
            inittime = datetime.datetime(1989,12,31)  + datetime.timedelta(seconds=point.dataDict['time'])
            self.xml.elem("time",inittime.strftime("%Y-%m-%dT%H:%M:%SZ"))
            self.xml.pop()

    def getTracks(self):
        self.gps.getTracks(self.getTracksFromGps)

        if not self.startTrackHeader:
            self.xml.pop()
            self.xml.pop()

    def getClose(self):
        self.xml.pop()

    def putWaypoints(self,file):
        self.contentHeader = GpxWaypointHandler()
        self.saxparser = make_parser()
        self.saxparser.setContentHandler(self.contentHeader)
        self.saxparser.parse(file)


        if debug:
            print "Send waypoints to gps :"
            print "----------------------"

            for x in self.contentHeader.waypoints:
                print x

        self.gps.putWaypoints(self.contentHeader.waypoints)

    def putRoutes(self,file):
        self.contentHeader = GpxRouteHandler()
        self.saxparser = make_parser()
        self.saxparser.setContentHandler(self.contentHeader)
        self.saxparser.parse(file)


        if debug:
            print "Send routes to gps :"
            print "----------------------"

            for route in self.contentHeader.routes:
                print route[0]

                for waypoint in route[1:]:
                    print "  ",waypoint

        self.gps.putRoutes(self.contentHeader.routes)

    def putTracks(self,file):
        self.contentHeader = GpxTrackHandler()
        self.saxparser = make_parser()
        self.saxparser.setContentHandler(self.contentHeader)
        self.saxparser.parse(file)

        if debug:
            print "Send tracks to gps :"
            print "----------------------"

            for track in self.contentHeader.tracks:
                print track[0]

                for waypoint in track[1:]:
                    print "  ",waypoint

        self.gps.putTracks(self.contentHeader.tracks)


''' Old code, too slow, was nearly finished, took another XMLWriter

class Gpx:

        def __init__(self,gps):
                self.gps = gps
                self.doc = minidom.Document()
                self.routenr = 0
                self.tracknr = 0

                self.doc.appendChild(self.doc.createComment('Try exporting to gpx format, nov 14 2004'))

                # Generate the gpx

                self.gpx = self.doc.createElement('gpx')
                self.gpx.setAttribute('version','1.1')
                self.gpx.setAttribute('creator','Pygarmin')
                self.gpx.setAttribute('xmlns:xsi','http://www.w3.org/2001/XMLSchema-instance')
                self.gpx.setAttribute('xmlns','http://www.topografix.com/GPX/1/1')
                self.gpx.setAttribute('xsi:schemaLocation','http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd')

                self.doc.appendChild(self.gpx)

        def getWaypointsFromGps(self,waypoint,recordnumber,totalWaypointsToGet,tp):
                # Generate waypoint

                wpt = self.doc.createElement('wpt')
                wpt.setAttribute('lat',str(degrees(waypoint.dataDict['slat'])))
                wpt.setAttribute('lon',str(degrees(waypoint.dataDict['slon'])))

                ele = self.doc.createElement('ele')
                ele.appendChild(self.doc.createTextNode(str(waypoint.dataDict['alt'])))

                name = self.doc.createElement('name')
                name.appendChild(self.doc.createTextNode(waypoint.dataDict['ident']))

                cmt = self.doc.createElement('cmt')
                cmt.appendChild(self.doc.createTextNode(waypoint.dataDict['cmnt']))

                wpt.appendChild(ele)
                wpt.appendChild(name)
                wpt.appendChild(cmt)

                self.gpx.appendChild(wpt)

        def getWaypoints(self):
                self.gps.getWaypoints(self.getWaypointsFromGps)

        def getRoutesFromGps(self,point,recordnumber,totalpointsToGet,tp):

                if isinstance(point,(garmin.RouteHdr)):

                        # Each gps has another route header
                        # D200 : nmbs
                        # D201 : nmbr,cmnt
                        # D202 : ident

                        self.routenr += 1

                        self.rte = self.doc.createElement('rte')

                        name = self.doc.createElement('name')

                        if point.dataDict.has_key('cmnt'):
                                name.appendChild(self.doc.createTextNode(point.dataDict['cmnt']))
                        elif point.dataDict.has_key('ident'):
                                name.appendChild(self.doc.createTextNode(point.dataDict['ident']))
                        else:
                                name.appendChild(self.doc.createTextNode('route' + str(self.routenr)))

                        number = self.doc.createElement('number')

                        if point.dataDict.has_key('nmbr'):
                                number.appendChild(self.doc.createTextNode(str(point.dataDict['nmbr'])))
                        else:
                                number.appendChild(self.doc.createTextNode(str(self.routenr)))

                        self.rte.appendChild(name)
                        self.rte.appendChild(number)

                        self.gpx.appendChild(self.rte)

                # I really don't want the D210_Rte_Link_Type

                elif not isinstance(point,garmin.RouteLink):

                        rtept = self.doc.createElement('rtept')
                        rtept.setAttribute('lat',str(degrees(point.dataDict['slat'])))
                        rtept.setAttribute('lon',str(degrees(point.dataDict['slon'])))

                        ele = self.doc.createElement('ele')
                        ele.appendChild(self.doc.createTextNode(str(point.dataDict['alt'])))

                        name = self.doc.createElement('name')
                        name.appendChild(self.doc.createTextNode(str(point.dataDict['ident'])))

                        cmt = self.doc.createElement('cmt')
                        cmt.appendChild(self.doc.createTextNode(str(point.dataDict['cmnt'])))

                        rtept.appendChild(ele)
                        rtept.appendChild(name)
                        rtept.appendChild(cmt)

                        self.rte.appendChild(rtept)

        def getRoutes(self):
                self.gps.getRoutes(self.getRoutesFromGps)

        def getTracksFromGps(self,point,recordnumber,totalPointsToGet,tp):
                #print recordnumber,point.dataDict

                if isinstance(point,garmin.TrackHdr):
                        self.trk = self.doc.createElement('trk')

                        name = self.doc.createElement('name')
                        name.appendChild(self.doc.createTextNode(str(point.dataDict['ident'])))

                        self.trk.appendChild(name)

                        self.gpx.appendChild(self.trk)
                else:xml.pop()

                        if point.dataDict['new_trk'] == True:
                                self.trkseg = self.doc.createElement('trkseg')
                                self.trk.appendChild(self.trkseg)

                        trkpt = self.doc.createElement('trkpt')
                        trkpt.setAttribute('lat',str(degrees(point.dataDict['slat'])))
                        trkpt.setAttribute('lon',str(degrees(point.dataDict['slon'])))

                        ele = self.doc.createElement('ele')
                        ele.appendChild(self.doc.createTexml.pop()xtNode(str(point.dataDict['alt'])))

                        trkpt.appendChild(ele)

                        self.trkseg.appendChild(trkpt)


        def getTracks(self):
                self.gps.getTracks(self.getTracksFromGps)
'''
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

    # Code for OziExplorer
    # Get info from GPS and store into OziExplorer

    if 0:
        ozie = OziExplorer(gps)

        print "Check the code:"
        print "---------------"
        print "Get the waypoint(s) and save them to the file: ozie.wpt"
        ozie.getWaypoints("ozie.wpt")
        print "Get the route(s) and save them to the file: ozie.rte"
        ozie.getRoutes("ozie.rte")
        print "Get the track(s) and save them to *.plt files"
        ozie.getTracks()

    # Sent OziExplorer to your GPS, change your path first !!

    if 0:
        ozie.putWaypoints("/path/to/ozie.wpt")
        ozie.putRoutes("/path/to/ozie.rte")
        ozie.putTracks("/path/to/ozie.plt")

    # Code for GPX
    # Get info from GPS and store into gpx format

    if 0:
        print "Check the code:"
        print "---------------"
        file = open('pygarmin.gpx','w')
        gpx = Gpx(gps)

        # Init some values

        gpx.getStart(file)

        print "Get the waypoint(s) and append to pygarmin.gpx"
        gpx.getWaypoints()
        print "Get the route(s) and append to pygarmin.gpx"
        gpx.getRoutes()
        print "Get the track(s) and append to pygarmin.gpx"
        gpx.getTracks()

        # Write "</gps>" to the file

        gpx.getClose()
        file.close()

        print "Everything is saved to pygarmin.gpx"

    # Sens gpx format to your GPS

    if 0:
        print "Check the code:"
        print "---------------"
        gpx = Gpx(gps)

        print "Send waypoints from pygarmin.gpx to your GPS"
        gpx.putWaypoints("pygarmin.gpx")
        print "Send routes from pygarmin.gpx to your GPS"
        gpx.putRoutes("pygarmin.gpx")
        print "Send tracks from pygarmin.gpx to your GPS"
        gpx.putTracks("pygarmin.gpx")

if __name__ == "__main__":
    main()
