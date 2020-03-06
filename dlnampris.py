'''
Copyright (c) 2020 Modul 9/HiFiBerry

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


Author: Modul 9 <info@hifiberry.com>
Based on mpDris2 by
         Jean-Philippe Braun <eon@patapon.info>,
         Mantas Mikulėnas <grawity@gmail.com>
Based on mpDris by:
         Erik Karlsson <pilo@ayeon.org>
Some bits taken from quodlibet mpris plugin by:
          <christoph.reiter@gmx.at>
'''


import sys
import logging
import time
import threading
import fcntl
import subprocess
import signal
from configparser import ConfigParser

import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import xmltodict

try:
    from gi.repository import GLib
    using_gi_glib = True
except ImportError:
    import glib as GLib
    
    
dlna_wrapper = None
glib_mainloop = None

identity = "dlna client"

PLAYBACK_STOPPED = "STOPPED"
PLAYBACK_PAUSED = "PAUSED_PLAYBACK"
PLAYBACK_PLAYING = "PLAYING"
PLAYBACK_UNKNOWN = "UNKNOWN"

# python dbus bindings don't include annotations and properties
MPRIS2_INTROSPECTION = """<node name="/org/mpris/MediaPlayer2">
  <interface name="org.freedesktop.DBus.Introspectable">
    <method name="Introspect">
      <arg direction="out" name="xml_data" type="s"/>
    </method>
  </interface>
  <interface name="org.freedesktop.DBus.Properties">
    <method name="Get">
      <arg direction="in" name="interface_name" type="s"/>
      <arg direction="in" name="property_name" type="s"/>
      <arg direction="out" name="value" type="v"/>
    </method>
    <method name="GetAll">
      <arg direction="in" name="interface_name" type="s"/>
      <arg direction="out" name="properties" type="a{sv}"/>
    </method>
    <method name="Set">
      <arg direction="in" name="interface_name" type="s"/>
      <arg direction="in" name="property_name" type="s"/>
      <arg direction="in" name="value" type="v"/>
    </method>
    <signal name="PropertiesChanged">
      <arg name="interface_name" type="s"/>
      <arg name="changed_properties" type="a{sv}"/>
      <arg name="invalidated_properties" type="as"/>
    </signal>
  </interface>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek">
      <arg direction="in" name="Offset" type="x"/>
    </method>
    <method name="SetPosition">
      <arg direction="in" name="TrackId" type="o"/>
      <arg direction="in" name="Position" type="x"/>
    </method>
    <method name="OpenUri">
      <arg direction="in" name="Uri" type="s"/>
    </method>
    <signal name="Seeked">
      <arg name="Position" type="x"/>
    </signal>
    <property name="PlaybackStatus" type="s" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="LoopStatus" type="s" access="readwrite">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="Rate" type="d" access="readwrite">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="Shuffle" type="b" access="readwrite">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="Metadata" type="a{sv}" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="Volume" type="d" access="readwrite">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
    </property>
    <property name="Position" type="x" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
    </property>
    <property name="MinimumRate" type="d" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="MaximumRate" type="d" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="CanGoNext" type="b" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="CanGoPrevious" type="b" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="CanPlay" type="b" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="CanPause" type="b" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="CanSeek" type="b" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="true"/>
    </property>
    <property name="CanControl" type="b" access="read">
      <annotation name="org.freedesktop.DBus.Property.EmitsChangedSignal" value="false"/>
    </property>
  </interface>
</node>"""


class DLNAWrapper(threading.Thread):
    """ 
    Wrapper to handle DLNA renderer (gmedia-render)
    """
    
    def __init__(self, auto_start = True):
        super().__init__()
        self.playerid = None
        self.playback_status =PLAYBACK_STOPPED
        self.metadata = {}
        self.dbus_service = None
        self.bus = dbus.SessionBus()
        self.finished = False
        self.process = None
        self.playback_url = None
        self.playback_metadata = {}
        
        
        self.uuid=""
        try:
            with open('/etc/uuid', 'r') as file:
                self.uuid = file.read().strip()
        except:
            pass
                
        if len(self.uuid) != 36:
            self.uuid="00000000-0000-0000-0000-000000000000"
            
        parser = ConfigParser()
        parser.read("/etc/dlnampris.conf")
        
        self.playername = parser.get("dlna-mpris","systemname",fallback="HiFiBerry")
        self.mixer =  parser.get("dlna-mpris","mixer",fallback="Softvol")

            
    def run(self):
        try:
            self.dbus_service = MPRISInterface()
            
            while not(self.finished):
                
                if self.process is None:
                    cmd = [
                        '/bin/gmediarender',
                        '-f', self.playername,
                        '--gstout-audiosink=alsasink',
                        '-u', self.uuid,
                         '--logfile=stdout',
                         '--mixer='+self.mixer
                        ]
                    logging.info("starting dlna server: %s", cmd)
                    self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                    
                if self.process.poll() is not None:
                    self.process = None
                    logging.info("dlna server server was terminated, trying to restart")
                    time.sleep(3)
                    continue
                
                line = self.process.stdout.readline().rstrip()
                self.parse_line(line)
                
        except Exception as e:
            logging.error("DLNAWrapper thread exception: %s", e)
        
    
    def terminate(self):
        logging.info("Terminating dlna server process")
        self.finished = True
        if self.process is not None:
            self.process.kill()

 
    def parse_line(self, line):
        # logging.info("LINE %s", line)
        
        updated = False
        
        xmldata = None
        
        if line.startswith(b"<"):
            try:
                xmldata = xmltodict.parse(line)
            except: 
                pass
  
        # Playback state
        try: 
            self.playback_status = xmldata["TransportState"]["@val"]
            updated = True
            
            if self.playback_status == PLAYBACK_STOPPED:
                self.playback_url = None
        except: 
            pass

        # Stream URL        
        try: 
            self.playback_url = xmldata["CurrentTrackURI"]["@val"]
            updated = True
            self.playback_metadata = {}
        except: 
            pass
        
        # Metadata
        try:
            metadata_str = xmldata["CurrentTrackMetaData"]["@val"]
            metadata = xmltodict.parse(metadata_str)
            item = metadata["DIDL-Lite"]["item"]
            logging.error("Item %s", item)
            
            self.metadata["xesam:title"] = str(item.get("dc:title"))
            self.metadata["xesam:artist"] = str(item.get("dc:creator"))
            self.metadata["xesam:album"] = str(item.get("upnp:album"))
            # self.metadata["mpris:artUrl"] = item.get("upnp:albumArtURI")
            for i in item.get("upnp:albumArtURI"):
                if i.startswith("http"):
                    logging.error("retrieving artwork not yet implemented")
                    
            self.metadata["xesam:trackNumber"] = item.get("upnp:originalTrackNumber")
            
            logging.error("got metadata: %s", self.metadata)
                    
            updated = True
        except:
            pass
        
        if updated:
            logging.error("got something %s", line)
                        
                        
    def stop(self):
        """
        Stop playback
        """
        if self.process is not None:
            self.process.kill()
        

    def update_metadata(self):        
        # TODO 

        self.dbus_service.update_property('org.mpris.MediaPlayer2.Player',
                                                  'Metadata')


class MPRISInterface(dbus.service.Object):
    ''' The base object of an MPRIS player '''

    PATH = "/org/mpris/MediaPlayer2"
    INTROSPECT_INTERFACE = "org.freedesktop.DBus.Introspectable"
    PROP_INTERFACE = dbus.PROPERTIES_IFACE

    def __init__(self):
        dbus.service.Object.__init__(self, dbus.SystemBus(),
                                     MPRISInterface.PATH)
        self.name = "org.mpris.MediaPlayer2.dlna"
        self.bus = dbus.SystemBus()
        self.uname = self.bus.get_unique_name()
        self.dbus_obj = self.bus.get_object("org.freedesktop.DBus",
                                            "/org/freedesktop/DBus")
        self.dbus_obj.connect_to_signal("NameOwnerChanged",
                                        self.name_owner_changed_callback,
                                        arg0=self.name)

        self.acquire_name()
        logging.info("name on DBus aqcuired")

    def name_owner_changed_callback(self, name, old_owner, new_owner):
        if name == self.name and old_owner == self.uname and new_owner != "":
            try:
                pid = self._dbus_obj.GetConnectionUnixProcessID(new_owner)
            except:
                pid = None
            logging.info("Replaced by %s (PID %s)" %
                         (new_owner, pid or "unknown"))
            loop.quit()

    def acquire_name(self):
        self.bus_name = dbus.service.BusName(self.name,
                                             bus=self.bus,
                                             allow_replacement=True,
                                             replace_existing=True)

    def release_name(self):
        if hasattr(self, "_bus_name"):
            del self.bus_name

    ROOT_INTERFACE = "org.mpris.MediaPlayer2"
    ROOT_PROPS = {
        "CanQuit": (False, None),
        "CanRaise": (False, None),
        "DesktopEntry": ("dlna", None),
        "HasTrackList": (False, None),
        "Identity": (identity, None),
        "SupportedUriSchemes": (dbus.Array(signature="s"), None),
        "SupportedMimeTypes": (dbus.Array(signature="s"), None)
    }

    @dbus.service.method(INTROSPECT_INTERFACE)
    def Introspect(self):
        return MPRIS2_INTROSPECTION

    def get_playback_status():
        status = dlna_wrapper.playback_status
        return {PLAYBACK_PLAYING: 'Playing',
                PLAYBACK_PAUSED: 'Paused',
                PLAYBACK_STOPPED: 'Stopped',
                PLAYBACK_UNKNOWN: 'Unknown'}[status]

    def get_metadata():
        return dbus.Dictionary(dlna_wrapper.metadata, signature='sv')

    PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
    PLAYER_PROPS = {
        "PlaybackStatus": (get_playback_status, None),
        "Rate": (1.0, None),
        "Metadata": (get_metadata, None),
        "MinimumRate": (1.0, None),
        "MaximumRate": (1.0, None),
        "CanGoNext": (False, None),
        "CanGoPrevious": (False, None),
        "CanPlay": (True, None),
        "CanPause": (False, None),
        "CanSeek": (False, None),
        "CanControl": (False, None),
    }

    PROP_MAPPING = {
        PLAYER_INTERFACE: PLAYER_PROPS,
        ROOT_INTERFACE: ROOT_PROPS,
    }

    @dbus.service.signal(PROP_INTERFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed_properties,
                          invalidated_properties):
        pass

    @dbus.service.method(PROP_INTERFACE,
                         in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        getter, _setter = self.PROP_MAPPING[interface][prop]
        if callable(getter):
            return getter()
        return getter

    @dbus.service.method(PROP_INTERFACE,
                         in_signature="ssv", out_signature="")
    def Set(self, interface, prop, value):
        _getter, setter = self.PROP_MAPPING[interface][prop]
        if setter is not None:
            setter(value)

    @dbus.service.method(PROP_INTERFACE,
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        read_props = {}
        props = self.PROP_MAPPING[interface]
        for key, (getter, _setter) in props.items():
            if callable(getter):
                getter = getter()
            read_props[key] = getter
        return read_props

    def update_property(self, interface, prop):
        getter, _setter = self.PROP_MAPPING[interface][prop]
        if callable(getter):
            value = getter()
        else:
            value = getter
        logging.debug('Updated property: %s = %s' % (prop, value))
        self.PropertiesChanged(interface, {prop: value}, [])
        return value

    # Player methods
    @dbus.service.method(PLAYER_INTERFACE, in_signature='', out_signature='')
    def Pause(self):
        logging.info("received DBUS pause, doing nothing")

    @dbus.service.method(PLAYER_INTERFACE, in_signature='', out_signature='')
    def PlayPause(self):
        logging.info("received DBUS playpause, doing nothing")


    @dbus.service.method(PLAYER_INTERFACE, in_signature='', out_signature='')
    def Stop(self):
        logging.debug("received DBUS stop, stopping playback")
        dlna_wrapper.stop()
        return

    @dbus.service.method(PLAYER_INTERFACE, in_signature='', out_signature='')
    def Play(self):
        logging.info("received DBUS play, doing nothing")
        # TODO
        return


def stop_playback(_signalNumber, _frame):
    logging.info("received USR1, stopping music playback")
    dlna_wrapper.stop()
    # TODO


def terminate(_signalNumber, _frame):
    logging.info("received TERM, stopping")
    dlna_wrapper.terminate()
    glib_mainloop.quit()
    # TODO    

if __name__ == '__main__':
    DBusGMainLoop(set_as_default=True)

    if len(sys.argv) > 1:
        if "-v" in sys.argv:
            logging.basicConfig(format='%(levelname)s: %(name)s - %(message)s',
                                level=logging.DEBUG)
            logging.debug("enabled verbose logging")
    else:
        logging.basicConfig(format='%(levelname)s: %(name)s - %(message)s',
                            level=logging.INFO)

    # Set up the main loop
    glib_mainloop = GLib.MainLoop()

    signal.signal(signal.SIGUSR1, stop_playback)
    signal.signal(signal.SIGTERM, terminate)

    # Create wrapper to handle connection failures with MPD more gracefully
    try:
        dlna_wrapper = DLNAWrapper()
        dlna_wrapper.start()
        logging.info("DLNA wrapper thread started")
    except dbus.exceptions.DBusException as e:
        logging.error("DBUS error: %s", e)
        sys.exit(1)

    time.sleep(2)
    if not (dlna_wrapper.is_alive()):
        logging.error("DLNA connector thread died, exiting")
        sys.exit(1)

    # Run idle loop
    try:
        logging.info("main loop started")
        glib_mainloop.run()
    except KeyboardInterrupt:
        logging.debug('Caught SIGINT, exiting.')
        
    dlna_wrapper.terminate()
