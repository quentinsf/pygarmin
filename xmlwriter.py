#!/usr/bin/env python
"""
   xmlwriter

   Helps in outputting nicely indented XML files.

   This is released under the Gnu General Public Licence. A copy of
   this can be found at http://www.opensource.org/licenses/gpl-license.html

   (c) 2001 Raymond Penners <raymond@dotsphinx.com>
   
"""

from sys import *

class XmlWriter:
   def __init__ (self, fname=None):
      self.indent_level = 0
      self.tag_stack = []
      if fname == None:
        self.f = stdout
      else:
        self.f = open(fname, "w")
      self.f.write("<?xml version=\"1.0\"?>")

   def __del__(self):
      self.f.close()

   def indent(self):
      self.f.write("\n")
      for i in range(0, self.indent_level):
         self.f.write("  ")
  
   def tag(self, name, isclosed=0, attributes={}):
      # Try and put tags like <title>Hello world</title> on one line
      if len(self.tag_stack) > 0:
         tag = self.tag_stack[len(self.tag_stack)-1]
         tag['subtags'] = 1
 
      self.indent()
      self.f.write("<" + name)
      for key in attributes.keys():
         self.f.write(" %s=\"%s\"" % (key, attributes[key]))
 
      if not isclosed:
         self.f.write(">")
         self.indent_level = self.indent_level + 1
         self.tag_stack.append({'tag':name, 'subtags':0})
      else:
         self.f.write("/>")

   def tagClose(self):
      self.indent_level = self.indent_level - 1
      tag = self.tag_stack.pop();
 
      # Try and put tags like <title>Hello world</title> on one line
      if tag['subtags']:
         self.indent()
 
      self.f.write("</%s>" % tag['tag'])

   def write(self,str):
      self.f.write(str)

def demo():
   x = XmlWriter();
   x.tag("gps", 0, {"class" : "garmin", "id" : "eTrex 2.10" })
   x.tag("waypoints")
   x.tag("waypoint", 0, {"class":"D100"})
   x.write('Hello')
   x.tagClose()
   x.tag("waypoint")
   x.write('Testing') 
   x.tag("another", 1)
   x.tag("tag", 1)
   x.tagClose()
   x.tagClose()
   x.tagClose()
  
if __name__=='__main__':
   demo()
