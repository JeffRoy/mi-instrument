#!/usr/bin/env python

"""
@package ion.agents.platform.rsn.rsn_platform_driver
@file    ion/agents/platform/rsn/rsn_platform_driver.py
@author  Carlos Rueda
@brief   The main RSN OMS platform driver class.
"""
import time
import logging
from mi.core.exceptions import InstrumentException

__author__ = 'Carlos Rueda'
__license__ = 'Apache 2.0'

from copy import deepcopy
import mi.core.log

log = mi.core.log.get_logger()
from functools import partial
from mi.core.common import BaseEnum
from mi.core.scheduler import PolledScheduler
from mi.platform.platform_driver import PlatformDriver
from mi.core.instrument.data_particle import DataParticle
from mi.core.instrument.instrument_driver import DriverAsyncEvent
from mi.platform.platform_driver import PlatformDriverState
from mi.platform.platform_driver import PlatformDriverEvent
from mi.platform.util.network import InstrumentNode
from mi.platform.exceptions import PlatformException
from mi.platform.exceptions import PlatformDriverException
from mi.platform.exceptions import PlatformConnectionException
from mi.platform.rsn.oms_client_factory import CIOMSClientFactory
from mi.platform.responses import NormalResponse, InvalidResponse


from mi.platform.platform_driver_event import OMSEventDriverEvent

# from pyon.util.containers import get_ion_ts

from mi.platform.util import ion_ts_2_ntp
import ntplib


# from pyon.event.event import EventSubscriber

# from pyon.agent.common import BaseEnum
# from pyon.agent.instrument_fsm import InstrumentException
# 
# from pyon.core.object import ion_serializer, IonObjectDeserializer
# from pyon.core.registry import IonObjectRegistry
# from ion.core.ooiref import OOIReferenceDesignator

from mi.platform.util.node_configuration import NodeConfiguration


 
 
class Platform_Particle(DataParticle):
    """
    The contents of the parameter dictionary, published at the start of a scan
    """
    def _build_parsed_values(self):
        
        
        
        
        return(self.raw_data)
    






class ScheduledJob(BaseEnum):
    """
    Instrument scheduled jobs
    """
    ACQUIRE_SAMPLE = 'pad_sample_timer_event'




class RSNPlatformDriverState(PlatformDriverState):
    """
    We simply inherit the states from the superclass
    """
    pass


class RSNPlatformDriverEvent(PlatformDriverEvent):
    """
    The ones for superclass plus a few others for the CONNECTED state.
    """
    CONNECT_INSTRUMENT        = 'RSN_PLATFORM_DRIVER_CONNECT_INSTRUMENT'
    DISCONNECT_INSTRUMENT     = 'RSN_PLATFORM_DRIVER_DISCONNECT_INSTRUMENT'
    GET_ENG_DATA              = 'RSN_PLATFORM_DRIVER_GET_ENG_DATA'
    TURN_ON_PORT              = 'RSN_PLATFORM_DRIVER_TURN_ON_PORT'
    TURN_OFF_PORT             = 'RSN_PLATFORM_DRIVER_TURN_OFF_PORT'
    START_PROFILER_MISSION    = 'RSN_PLATFORM_DRIVER_START_PROFILER_MISSION'
    ABORT_PROFILER_MISSION    = 'RSN_PLATFORM_DRIVER_ABORT_PROFILER_MISSION'
    CHECK_SYNC                = 'RSN_PLATFORM_DRIVER_CHECK_SYNC'


class RSNPlatformDriverCapability(BaseEnum):
    CONNECT_INSTRUMENT        = RSNPlatformDriverEvent.CONNECT_INSTRUMENT
    DISCONNECT_INSTRUMENT     = RSNPlatformDriverEvent.DISCONNECT_INSTRUMENT
    GET_ENG_DATA              = RSNPlatformDriverEvent.GET_ENG_DATA
    TURN_ON_PORT              = RSNPlatformDriverEvent.TURN_ON_PORT
    TURN_OFF_PORT             = RSNPlatformDriverEvent.TURN_OFF_PORT
    START_PROFILER_MISSION    = RSNPlatformDriverEvent.START_PROFILER_MISSION
    ABORT_PROFILER_MISSION    = RSNPlatformDriverEvent.ABORT_PROFILER_MISSION
 
    
#    OOIION-1623 Remove until Check Sync requirements fully defined
#    CHECK_SYNC                = RSNPlatformDriverEvent.CHECK_SYNC


class RSNPlatformDriver(PlatformDriver):
    """
    The main RSN OMS platform driver class.
    """
    def __init__(self, event_callback):
        """
        Creates an RSNPlatformDriver instance.

        @param pnode           Root PlatformNode defining the platform network
                               rooted at this platform.
        @param event_callback  Listener of events generated by this driver
        """
        PlatformDriver.__init__(self, event_callback)

        # CIOMSClient instance created by connect() and destroyed by disconnect():
        self._rsn_oms = None

 

        # URL for the event listener registration/unregistration (based on
        # web server launched by ServiceGatewayService, since that's the
        # service in charge of receiving/relaying the OMS events).
        # NOTE: (as proposed long ago), this kind of functionality should
        # actually be provided by some component more in charge of the RSN
        # platform netwokr as a whole -- as opposed to platform-specific).
        self.listener_url = None
        
               # scheduler config is a bit redundant now, but if we ever want to
        # re-initialize a scheduler we will need it.
        self._scheduler = None
        
        
     

        
        

    def _filter_capabilities(self, events):
        """
        """
        events_out = [x for x in events if RSNPlatformDriverCapability.has(x)]
        return events_out

    def validate_driver_configuration(self, driver_config):
        """
        Driver config must include 'oms_uri' entry.
        """
        if not 'oms_uri' in driver_config:
            log.error("'oms_uri' not present in driver_config = %s", driver_config)
            raise PlatformDriverException(msg="driver_config does not indicate 'oms_uri'")

    def _configure(self, driver_config):
        """
        Nothing special done here, only calls super.configure(driver_config)

        @param driver_config with required 'oms_uri' entry.
        """
        PlatformDriver._configure(self, driver_config)

        self.nodeCfgFile = NodeConfiguration()
 
        
        self._platform_id = driver_config['node_id']
            
        
        self.nodeCfgFile.Open(self._platform_id,driver_config['driver_config_file']['default_cfg_file'],driver_config['driver_config_file']['node_cfg_file'])

        self.nodeCfgFile.Print();
        
        self._construct_resource_schema()
        
        
    def _build_scheduler(self):
        """
        Build a scheduler for periodic status updates
        """
        self._scheduler = PolledScheduler()
        self._scheduler.start()
        
        def event_callback(self, event):
            log.info("driver job triggered, raise event: %s" % event)
            self._fsm.on_event(event)

        # Dynamically create the method and add it
        method = partial(event_callback, self, RSNPlatformDriverEvent.GET_ENG_DATA)
        
        
        self._job = self._scheduler.add_interval_job(method, seconds=3)
       

    def _delete_scheduler(self):
        """
        Remove the autosample schedule.
        """
        try:
            self._scheduler.remove_scheduler(self._job)
        except KeyError:
            log.info('Failed to remove scheduled job for ACQUIRE_SAMPLE')
        
    
    def _construct_resource_schema(self):
        """
        """
        parameters = deepcopy(self._param_dict)

        for k,v in parameters.iteritems():
            read_write = v.get('read_write', None)
            if read_write == 'write':
                v['visibility'] = 'READ_WRITE'
            else:
                v['visibility'] = 'READ_ONLY'

        commands = {}
        commands[RSNPlatformDriverEvent.TURN_ON_PORT] = \
            {
                "display_name" : "Port Power On",
                "description" : "Activate port power.",
                "args" : [],
                "kwargs" : {
                       'port_id' : {
                            "required" : True,
                            "type" : "int",
                        }
                }

            }
        commands[RSNPlatformDriverEvent.TURN_OFF_PORT] = \
            {
                "display_name" : "Port Power Off",
                "description" : "Deactivate port power.",
                "args" : [],
                "kwargs" : {
                       'port_id' : {
                            "required" : True,
                            "type" : "int",
                        }
                }
            }
 
        self._resource_schema['parameters'] = parameters
        self._resource_schema['commands'] = commands

    def _ping(self):
        """
        Verifies communication with external platform returning "PONG" if
        this verification completes OK.

        @retval "PONG" iff all OK.
        @raise PlatformConnectionException Cannot ping external platform or
               got unexpected response.
        """
        log.debug("%r: pinging OMS...", self._platform_id)
        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot ping: _rsn_oms object required (created via connect() call)")

        try:
            retval = self._rsn_oms.hello.ping()
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot ping: %s" % str(e))

        if retval is None or retval.upper() != "PONG":
            raise PlatformConnectionException(msg="Unexpected ping response: %r" % retval)

        log.debug("%r: ping completed: response: %s", self._platform_id, retval)

        return "PONG"

    def callback_for_alert(self, event, *args, **kwargs):
        log.debug("caught an OMSDeviceStatusEvent: %s", event)       
        
#        self._notify_driver_event(OMSEventDriverEvent(event['description']))
     
        log.info('Platform agent %r published OMSDeviceStatusEvent : %s, time: %s',
                 self._platform_id, event, time.time())


    
    def _connect(self, recursion=None):
        """
        Creates an CIOMSClient instance, does a ping to verify connection,
        and starts event dispatch.
        """
        # create CIOMSClient:
        oms_uri = self._driver_config['oms_uri']
        log.debug("%r: creating CIOMSClient instance with oms_uri=%r",
                  self._platform_id, oms_uri)
        self._rsn_oms = CIOMSClientFactory.create_instance(oms_uri)
        log.debug("%r: CIOMSClient instance created: %s",
                  self._platform_id, self._rsn_oms)

        # ping to verify connection:
        self._ping()

        # start event dispatch:
        self._start_event_dispatch()
        
        
        self._build_scheduler()

        # TODO - commented out
        # self.event_subscriber = EventSubscriber(event_type='OMSDeviceStatusEvent',
        #     callback=self.callback_for_alert)
        #
        # self.event_subscriber.start()

 

    def _disconnect(self, recursion=None):
        """
        Stops event dispatch and destroys the CIOMSClient instance.
        """
        self._stop_event_dispatch()
        self.event_subscriber.stop()
        self.event_subscriber=None
  

        CIOMSClientFactory.destroy_instance(self._rsn_oms)
        self._rsn_oms = None
        log.debug("%r: CIOMSClient instance destroyed", self._platform_id)
        
        self._delete_scheduler();
        self._scheduler = None
        

    def get_metadata(self):
        """
        """
        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot get_platform_metadata: _rsn_oms object required (created via connect() call)")
        try:
            retval = self._rsn_oms.config.get_platform_metadata(self._platform_id)
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot get_platform_metadata: %s" % str(e))

        log.debug("get_platform_metadata = %s", retval)

        if not self._platform_id in retval:
            raise PlatformException("Unexpected: response does not include "
                                    "requested platform '%s'" % self._platform_id)

        md = retval[self._platform_id]
        return md

   
    def get_eng_data(self):
        
        log.debug("%r: get_eng_data...", self._platform_id)
        
        numSeconds = 10.0
       
        ntp_time = ntplib.system_to_ntp_time(time.time())
        
        start_time = ntp_time -numSeconds
        
        attrs = [('sec_node_port_J5_IP1_output_current',start_time),
                 ('sec_node_port_J5_IP1_output_voltage',start_time),
                 ('sec_node_port_J5_IP1_output_temperature',start_time),
                 ('sec_node_port_J5_IP1_gfd_high',start_time),
                 ('sec_node_port_J5_IP1_gfd_low',start_time),
                 ('sec_node_port_J5_IP1_board_state',start_time),
                 ('sec_node_port_J5_IP1_error_state',start_time),
                 ('sec_node_port_J5_IP1_gpio_state',start_time),
                 ('sec_node_port_J5_IP1_ocd_current',start_time),
                 ('sec_node_port_J5_IP1_ocd_time_const',start_time)]
        

        returnDict = self.get_attribute_values(attrs)
        
        pad_particle = Platform_Particle(returnDict,port_timestamp=ntp_time)
        
        pad_particle.set_internal_timestamp(timestamp=ntp_time)
        
        pad_particle._data_particle_type = 'MJ01A_sec_node_port_J5_IP1'  # stream name
        
        json_message = pad_particle.generate() # this cals parse values above to go from raw to values dict
      
      
        event = {
            'type': DriverAsyncEvent.SAMPLE,
            'value': json_message,
            'time': time.time()
        }
      
        self._send_event(event)
#TODO need error handling                                                
#        returnList = returnDict[nodeName][attributeName]
        
        

        
        
        
        
        return 1

    def get_attribute_values(self, attrs):
        """
        """
        if not isinstance(attrs, (list, tuple)):
            raise PlatformException('get_attribute_values: attrs argument must be a '
                                    'list [(attrName, from_time), ...]. Given: %s', attrs)

        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot get_platform_attribute_values: _rsn_oms object required (created via connect() call)")

        # convert the ION system time from_time to NTP, as this is the time
        # format used by the RSN OMS interface:
        
        # also convert the ION parameter names to RSN attribute IDs
        attrs_ntp = [(self.nodeCfgFile.GetAttrFromParameter(attr_id), from_time)
                     for (attr_id, from_time) in attrs]
        
        
        
        
        log.debug("get_attribute_values(ntp): attrs=%s", attrs_ntp)

        try:
            retval = self._rsn_oms.attr.get_platform_attribute_values(self._platform_id,
                                                                      attrs_ntp)
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot get_platform_attribute_values: %s" % str(e))

        if not self._platform_id in retval:
            raise PlatformException("Unexpected: response does not include "
                                    "requested platform '%s'" % self._platform_id)

        attr_values = retval[self._platform_id]
        
        attrs_return = {}
        
        #convert back to ION parameter name and scale from OMS to ION
        for key in attr_values :
            newAttrList = []
            scaleFactor = self.nodeCfgFile.GetScaleFactorFromAttr(key)
            for v, ts in attr_values[key]:
                newAttrList.append((v*scaleFactor,ts))
            attrs_return[self.nodeCfgFile.GetParameterFromAttr(key)] = newAttrList
            
        log.debug("Back to ION=%s", attrs_return)

        

        # reported timestamps are already in NTP. Just return the dict:
        return attrs_return

    def _validate_set_attribute_values(self, attrs):
        """
        Does some pre-validation of the passed values according to the
        definition of the attributes.

        NOTE: We don't check everything here, just some basics.
        TODO determine appropriate validations at this level.
        Note that the basic checks here follow what the OMS system
        will do if we just send the request directly to it. So,
        need to determine what exactly should be done on the CI side.

        @param attrs

        @return dict of errors for the offending attribute names, if any.
        """
        # TODO determine appropriate validations at this level.

        # get definitions to verify the values against
        attr_defs = self._get_platform_attributes()

        log.debug("validating passed attributes: %s against defs %s", attrs, attr_defs)

        # to collect errors, if any:
        error_vals = {}
        for attr_name, attr_value in attrs:

            attr_def = attr_defs.get(attr_name, None)

            log.debug("validating %s against %s", attr_name, str(attr_def))

            if not attr_def:
                error_vals[attr_name] = InvalidResponse.ATTRIBUTE_ID
                log.warn("Attribute %s not in associated platform %s",
                         attr_name, self._platform_id)
                continue

            type_ = attr_def.get('type', None)
            units = attr_def.get('units', None)
            min_val = attr_def.get('min_val', None)
            max_val = attr_def.get('max_val', None)
            read_write = attr_def.get('read_write', None)
            group = attr_def.get('group', None)

            if "write" != read_write:
                error_vals[attr_name] = InvalidResponse.ATTRIBUTE_NOT_WRITABLE
                log.warn(
                    "Trying to set read-only attribute %s in platform %s",
                    attr_name, self._platform_id)
                continue

            #
            # TODO the following value-related checks are minimal
            #
            if type_ in ["float", "int"]:
                if min_val and float(attr_value) < float(min_val):
                    error_vals[attr_name] = InvalidResponse.ATTRIBUTE_VALUE_OUT_OF_RANGE
                    log.warn(
                        "Value %s for attribute %s is less than specified minimum "
                        "value %s in associated platform %s",
                        attr_value, attr_name, min_val,
                        self._platform_id)
                    continue

                if max_val and float(attr_value) > float(max_val):
                    error_vals[attr_name] = InvalidResponse.ATTRIBUTE_VALUE_OUT_OF_RANGE
                    log.warn(
                        "Value %s for attribute %s is greater than specified maximum "
                        "value %s in associated platform %s",
                        attr_value, attr_name, max_val,
                        self._platform_id)
                    continue

        return error_vals

    def set_attribute_values(self, attrs):
        """
        """
        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot set_platform_attribute_values: _rsn_oms object required (created via connect() call)")

        error_vals = self._validate_set_attribute_values(attrs)
        if len(error_vals) > 0:
            # remove offending attributes for the request below
            attrs_dict = dict(attrs)
            for bad_attr_name in error_vals:
                del attrs_dict[bad_attr_name]

            # no good attributes at all?
            if len(attrs_dict) == 0:
                # just immediately return with the errors:
                return error_vals

            # else: update attrs with the good attributes:
            attrs = attrs_dict.items()

        # ok, now make the request to RSN OMS:
        try:
            retval = self._rsn_oms.attr.set_platform_attribute_values(self._platform_id,
                                                                      attrs)
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot set_platform_attribute_values: %s" % str(e))

        log.debug("set_platform_attribute_values = %s", retval)

        if not self._platform_id in retval:
            raise PlatformException("Unexpected: response does not include "
                                    "requested platform '%s'" % self._platform_id)

        attr_values = retval[self._platform_id]

        # Note that the reported timestamps are in NTP.
        # (Timestamps indicate the time when the value was set for each attribute.)

        # ret_attr_values: dictionary to return, initialized with the error ones
        # determined above, if any:
        ret_attr_values = error_vals

        # add the info returned from RSN OMS:
        for attr_name, attr_val_ts in attr_values.iteritems():
            ret_attr_values[attr_name] = attr_val_ts

        log.debug("set_attribute_values: returning %s", ret_attr_values)

        return ret_attr_values

    def _verify_platform_id_in_response(self, response):
        """
        Verifies the presence of my platform_id in the response.

        @param response Dictionary returned by _rsn_oms

        @retval response[self._platform_id]
        """
        if not self._platform_id in response:
            msg = "unexpected: response does not contain entry for %r" % self._platform_id
            log.error(msg)
            raise PlatformException(msg=msg)

        if response[self._platform_id] == InvalidResponse.PLATFORM_ID:
            msg = "response reports invalid platform_id for %r" % self._platform_id
            log.error(msg)
            raise PlatformException(msg=msg)
        else:
            return response[self._platform_id]

    def _verify_port_id_in_response(self, port_id, dic):
        """
        Verifies the presence of port_id in the dic.

        @param port_id  The ID to verify
        @param dic Dictionary returned by _rsn_oms

        @return dic[port_id]
        """
        if not port_id in dic:
            msg = "unexpected: dic does not contain entry for %r" % port_id
            log.error(msg)
            #raise PlatformException(msg=msg)

        if dic[port_id] == InvalidResponse.PORT_ID:
            msg = "%r: response reports invalid port_id for %r" % (
                                 self._platform_id, port_id)
            log.error(msg)
            #raise PlatformException(msg=msg)
        else:
            return dic[port_id]

    

    
    

    def turn_on_port(self, port_id):
         
         
        try: 
            oms_port_id = self.nodeCfgFile.GetOMSPortId(port_id);
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot turn_on_platform_port: %s" % str(e))
        

        
        log.debug("%r: turning on port: port_id=%s oms port_id = %s",
                  self._platform_id, port_id,oms_port_id)
 
        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot turn_on_platform_port: _rsn_oms object required (created via connect() call)")

        try:
            response = self._rsn_oms.port.turn_on_platform_port(self._platform_id,
                                                                oms_port_id,'CI - User')
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot turn_on_platform_port: %s" % str(e))

        log.debug("%r: turn_on_platform_port response: %s",
                  self._platform_id, response)

        dic_plat = self._verify_platform_id_in_response(response)
        self._verify_port_id_in_response(oms_port_id, dic_plat)

        return dic_plat  # note: return the dic for the platform

    def turn_off_port(self, port_id):

        try: 
            oms_port_id = self.nodeCfgFile.GetOMSPortId(port_id);
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot turn_off_platform_port: %s" % str(e))
  
        log.debug("%r: turning off port: port_id=%s oms port_id = %s",
                  self._platform_id, port_id,oms_port_id)

 

        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot turn_off_platform_port: _rsn_oms object required (created via connect() call)")

        try:
            response = self._rsn_oms.port.turn_off_platform_port(self._platform_id,
                                                                 oms_port_id,'CI - User')
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot turn_off_platform_port: %s" % str(e))

        log.debug("%r: turn_off_platform_port response: %s",
                  self._platform_id, response)

        dic_plat = self._verify_platform_id_in_response(response)
        self._verify_port_id_in_response(oms_port_id, dic_plat)

        return dic_plat  # note: return the dic for the platform
    
    def start_profiler_mission(self, mission_name):
        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot start_profiler_mission: _rsn_oms object required (created via connect() call)")

        try:
            response = self._rsn_oms.port.start_profiler_mission(self._platform_id,
                                                                mission_name)
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot start_profiler_mission: %s" % str(e))

        log.debug("%r: start_profiler_mission response: %s",
                  self._platform_id, response)

        dic_plat = self._verify_platform_id_in_response(response)
        # TODO commented
        #self._verify_port_id_in_response(port_id, dic_plat)

        return dic_plat  # note: return the dic for the platform

    def abort_profiler_mission(self):
        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot abort_profiler_mission: _rsn_oms object required (created via connect() call)")

        try:
            response = self._rsn_oms.profiler.abort_profiler_mission(self._platform_id)
        except Exception as e:
            raise PlatformConnectionException(msg="Cannot abort_profiler_mission: %s" % str(e))

        log.debug("%r: abort_profiler_mission response: %s",
                  self._platform_id, response)

        dic_plat = self._verify_platform_id_in_response(response)
        # TODO commented
        #self._verify_port_id_in_response(port_id, dic_plat)

        return dic_plat  # note: return the dic for the platform


    ###############################################
    # External event handling:

    def _register_event_listener(self, url):
        """
        Registers given url for all event types.
        """
        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot _register_event_listener: _rsn_oms object required (created via connect() call)")

        try:
            already_registered = self._rsn_oms.event.get_registered_event_listeners()
        except Exception as e:
            raise PlatformConnectionException(
                msg="%r: Cannot get registered event listeners: %s" % (self._platform_id, e))

        if url in already_registered:
            log.debug("listener %r was already registered", url)
            return

        try:
            result = self._rsn_oms.event.register_event_listener(url)
        except Exception as e:
            raise PlatformConnectionException(
                msg="%r: Cannot register_event_listener: %s" % (self._platform_id, e))

        log.debug("%r: register_event_listener(%r) => %s", self._platform_id, url, result)

    def _unregister_event_listener(self, url):
        """
        Unregisters given url for all event types.
        """
        if self._rsn_oms is None:
            raise PlatformConnectionException("Cannot _unregister_event_listener: _rsn_oms object required (created via connect() call)")

        try:
            result = self._rsn_oms.event.unregister_event_listener(url)
        except Exception as e:
            raise PlatformConnectionException(
                msg="%r: Cannot unregister_event_listener: %s" % (self._platform_id, e))

        log.debug("%r: unregister_event_listener(%r) => %s", self._platform_id, url, result)

    def _start_event_dispatch(self):
        """
        Registers the event listener by using a URL that is composed from
        CFG.server.oms.host, CFG.server.oms.port, and CFG.server.oms.path.

        NOTE: the same listener URL will be registered by multiple RSN platform
        drivers. See other related notes in this file.

        @see https://jira.oceanobservatories.org/tasks/browse/OOIION-1287
        @see https://jira.oceanobservatories.org/tasks/browse/OOIION-968
        """

        # gateway host and port to compose URL:
        # TODO commented
        # host = CFG.get_safe('server.oms.host', "localhost")
        # port = CFG.get_safe('server.oms.port', "5000")
        # path = CFG.get_safe('server.oms.path', "/ion-service/oms_event")

        #the above are defined in pyon.cfg
        #we will override local host for debugging inside the VM
        host = "10.208.79.19"
        # TODO commented
        # self.listener_url = "http://%s:%s%s" % (host, port, path)
        # self._register_event_listener(self.listener_url)

        return "OK"

    def _stop_event_dispatch(self):
        """
        Stops the dispatch of events received from the platform network.

        NOTE: Nothing is actually done here: since the same listener URL
        is registered by multiple RSN platform drivers, we avoid unregistering
        it here because it might affect other drivers still depending on the
        events being notified.

        @see https://jira.oceanobservatories.org/tasks/browse/OOIION-968
        """

        log.debug("%r: Not unregistering listener URL to avoid affecting "
                  "other RSN platform drivers", self._platform_id)

        # unregister listener:
        #self._unregister_event_listener(self.listener_url)
        # NOTE: NO, DON'T unregister: other drivers might still be depending
        # on the listener being registered.

        return "OK"

   


    ##############################################################
    # GET
    ##############################################################

    def get(self, *args, **kwargs):

        if 'attrs' in kwargs:
            attrs = kwargs['attrs']
            result = self.get_attribute_values(attrs)
            return result


        if 'metadata' in kwargs:
            result = self.get_metadata()
            return result

        return super(RSNPlatformDriver, self).get(*args, **kwargs)

    ##############################################################
    # EXECUTE
    ##############################################################

    def execute(self, cmd, *args, **kwargs):
        """
        Executes the given command.

        @param cmd   command

        @return  result of the execution
        """


        if cmd == RSNPlatformDriverEvent.TURN_ON_PORT:
            result = self.turn_on_port(*args, **kwargs)

        elif cmd == RSNPlatformDriverEvent.TURN_OFF_PORT:
            result = self.turn_off_port(*args, **kwargs)
          
        elif cmd == RSNPlatformDriverEvent.START_PROFILER_MISSION:
            result = self.start_profiler_mission(*args, **kwargs)

        elif cmd == RSNPlatformDriverEvent.ABORT_PROFILER_MISSION:
            result = self.abort_profiler_mission(*args, **kwargs)

        else:
            result = super(RSNPlatformDriver, self).execute(cmd, args, kwargs)

        return result

    def _get_ports(self):
        ports = {}
        for port_id, port in self._pnode.ports.iteritems():
            ports[port_id] = {'state':   port.state}
        log.debug("%r: _get_ports: %s", self._platform_id, ports)
        return ports

    
    
    def _handler_connected_start_profiler_mission(self, *args, **kwargs):
        """
        """
#        profile_mission_name = kwargs.get('profile_mission_name', None)
        profile_mission_name = kwargs.get('profile_mission_name', 'Test_Profile_Mission_Name')
        if profile_mission_name is None :
            raise InstrumentException('start_profiler_mission: missing profile_mission_name argument')


        try:
            result = self.start_profiler_mission(profile_mission_name)
            return None, result

        except PlatformConnectionException as e:
            return self._connection_lost(RSNPlatformDriverEvent.START_PROFILER_MISSION,
                                         args, kwargs, e)
            
            
    def _handler_connected_get_eng_data(self, *args, **kwargs):
        """
        """

        try:
            result = self.get_eng_data()
            return None, result

        except PlatformConnectionException as e:
            return self._connection_lost(RSNPlatformDriverEvent.GET_ENG_DATA,
                                         args, kwargs, e)
            
    def _handler_connected_abort_profiler_mission(self, *args, **kwargs):
        """
        """
        try:
            result = self.abort_profiler_mission()
            return None, result

        except PlatformConnectionException as e:
            return self._connection_lost(RSNPlatformDriverEvent.ABORT_PROFILER_MISSION,
                                         args, kwargs, e)
    

    def _handler_connected_turn_on_port(self, *args, **kwargs):
        """
        """
        port_id = kwargs.get('port_id', None)
        if port_id is None:
            raise InstrumentException('turn_on_port: missing port_id argument')

        try:
            result = self.turn_on_port(port_id)
            return None, result

        except PlatformConnectionException as e:
            return self._connection_lost(RSNPlatformDriverEvent.TURN_ON_PORT,
                                         args, kwargs, e)

    def _handler_connected_turn_off_port(self, *args, **kwargs):
        """
        """
        port_id = kwargs.get('port_id', None)
        if port_id is None:
            raise InstrumentException('turn_off_port: missing port_id argument')

        try:
            result = self.turn_off_port(port_id)
            return None, result

        except PlatformConnectionException as e:
            return self._connection_lost(RSNPlatformDriverEvent.TURN_OFF_PORT,
                                         args, kwargs, e)

    
    ##############################################################
    # RSN Platform driver FSM setup
    ##############################################################

    def _construct_fsm(self,
                       states=RSNPlatformDriverState,
                       events=RSNPlatformDriverEvent,
                       enter_event=RSNPlatformDriverEvent.ENTER,
                       exit_event=RSNPlatformDriverEvent.EXIT):
        """
        """
        super(RSNPlatformDriver, self)._construct_fsm(states, events,
                                                      enter_event, exit_event)

        # CONNECTED state event handlers we add in this class:
        self._fsm.add_handler(PlatformDriverState.CONNECTED, RSNPlatformDriverEvent.TURN_ON_PORT, self._handler_connected_turn_on_port)
        self._fsm.add_handler(PlatformDriverState.CONNECTED, RSNPlatformDriverEvent.TURN_OFF_PORT, self._handler_connected_turn_off_port)
        self._fsm.add_handler(PlatformDriverState.CONNECTED, RSNPlatformDriverEvent.START_PROFILER_MISSION, self._handler_connected_start_profiler_mission)
        self._fsm.add_handler(PlatformDriverState.CONNECTED, RSNPlatformDriverEvent.ABORT_PROFILER_MISSION, self._handler_connected_abort_profiler_mission)
        self._fsm.add_handler(PlatformDriverState.CONNECTED, RSNPlatformDriverEvent.GET_ENG_DATA, self._handler_connected_get_eng_data)
        self._fsm.add_handler(PlatformDriverState.CONNECTED, ScheduledJob.ACQUIRE_SAMPLE, self._handler_connected_get_eng_data)
