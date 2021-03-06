# Copyright 2016 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import traceback

import atexit
import contextlib
import uuid

from oslo_config import cfg
from oslo_log import log as logging
import paramiko
import tenacity
from tooz import coordination

from networking_generic_switch import devices
from networking_generic_switch import exceptions as exc
from networking_generic_switch import locking as ngs_lock

import logging
import corsavfc
import requests
import json
import sys

import time

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class CorsaSwitch(devices.GenericSwitchDevice):

    ADD_NETWORK = None

    DELETE_NETWORK = None

    PLUG_PORT_TO_NETWORK = None

    DELETE_PORT = None

    SAVE_CONFIGURATION = None

    def __init__(self, device_cfg):
        super(CorsaSwitch, self).__init__(device_cfg)
        device_type = self.config.get('device_type', '')
        # use part that is after 'netmiko_'
        device_type = device_type.partition('corsa_')[2]
        #if device_type not in netmiko.platforms:
        #    raise exc.GenericSwitchNetmikoNotSupported(
        #        device_type=device_type)
        self.config['device_type'] = device_type

        self.locker = None
        if CONF.ngs_coordination.backend_url:
            self.locker = coordination.get_coordinator(
                CONF.ngs_coordination.backend_url,
                ('ngs-' + CONF.host).encode('ascii'))
            self.locker.start()
            atexit.register(self.locker.stop)

        self.lock_kwargs = {
            'locks_pool_size': int(self.ngs_config['ngs_max_connections']),
            'locks_prefix': self.config.get(
                'host', '') or self.config.get('ip', ''),
            'timeout': CONF.ngs_coordination.acquire_timeout}
        
    def _format_commands(self, commands, **kwargs):
        if not commands:
            return
        if not all(kwargs.values()):
            raise exc.GenericSwitchNetmikoMethodError(cmds=commands,
                                                      args=kwargs)
        try:
            cmd_set = [cmd.format(**kwargs) for cmd in commands]
        except (KeyError, TypeError):
            raise exc.GenericSwitchNetmikoMethodError(cmds=commands,
                                                      args=kwargs)
        return cmd_set

    def add_network(self, segmentation_id, network_id, project_id=None, of_controller=None, vfc_name=None):
        token = self.config['token']
        headers = {'Authorization': token}
                
        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
                
        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr
                
        #./create-vfc.py br1 5 openflow VFC-1 192.168.201.164 6653 100-105
        c_br_res =  self.config['defaultVFCRes']
        c_br_type = self.config['VFCType']

        c_vlan = segmentation_id
        c_uplink_ports = self.config['uplink_ports']

        c_br_type = self.config['VFCType']
        
        cont_ip = self.config['defaultControllerIP']
        cont_port = self.config['defaultControllerPort']
        c_controller_namespace = 'default'
        c_vfc_name = self.config['defaultVFCName']

        if of_controller:
            cont_ip, cont_port = of_controller
            if 'controllerNamespace' in self.config:
                c_controller_namespace = self.config['controllerNamespace']

        if vfc_name:
            c_vfc_name = str(vfc_name) 
        else:
            c_vfc_name = project_id + "-" + c_vfc_name
        

        c_br_descr = c_vfc_name + "-VLAN-" + str(segmentation_id)
         
        isVFCHost = True
        if not 'VFCHost' in self.config or not self.config['VFCHost'] == 'True':
            LOG.info("PRUTH: Skipping VFC Creation: isVFCHost " + str(isVFCHost))
            isVFCHost = False
            return

   
        LOG.info("controller:  cont_ip =  " + str(cont_ip) + ", cont_port = " + str(cont_port) + ", c_controller_namespace = " + str(c_controller_namespace))
        LOG.info("segmentation_id    " + str(segmentation_id)) 
        LOG.info("provisioning vlan  " + str(self.config['provisioningVLAN']))
        LOG.info("PRUTH: isVFCHost " + str(isVFCHost))
        LOG.info("PRUTH: --- vfc_name " + str(c_vfc_name))

        try:
            if self.config.has_key('provisioningVLAN'):
                if str(segmentation_id) == self.config['provisioningVLAN']:
                    LOG.info("Creating provisioning network on VLAN " + self.config['provisioningVLAN'] + " with controller " + self.config['provisioningControllerPort'] + ":" + self.config['provisioningControllerPort'])
                    c_br_type = self.config['provisioningVFCType']
                    cont_ip = self.config['provisioningControllerIP']
                    cont_port = self.config['provisioningControllerPort']
        except Exception as e:
            LOG.error("Failed to find provisioning network controller.  Using default controller")

        
        c_br = None
        try:
            with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):
                c_br = corsavfc.get_free_bridge(headers, url_switch)
                cont_id = 'CONT' + str(c_br) 
                
                #Create the bridge
                corsavfc.bridge_create(headers, url_switch, c_br, br_subtype = c_br_type, br_resources = c_br_res, br_descr=c_br_descr, br_namespace=c_controller_namespace)
                #Add the controller
                LOG.info("Attaching of_controller " + str(cont_ip) + ":" + str(cont_port) + " to bridge " + str(c_br))
                corsavfc.bridge_add_controller(headers, url_switch, br_id = c_br, cont_id = cont_id, cont_ip = cont_ip, cont_port = cont_port)
                
                LOG.info("About to get_ofport: c_br: " + str(c_br) + ", c_uplink_ports: " + str(c_uplink_ports))
                for uplink in c_uplink_ports.split(','):
                     #Attach the uplink tunnel
                     LOG.info("About to get_ofport: c_br: " + str(c_br) + ", uplink: " + str(uplink)) 
                     #The logical port number of an uplink is assumed to be the VLAN id
                     ofport=c_vlan
                     LOG.info("ofport: " + str(ofport))
                     corsavfc.bridge_attach_tunnel_ctag_vlan(headers, url_switch, br_id = c_br, ofport = ofport, port = int(uplink), vlan_id = c_vlan)

        except Exception as e:
            LOG.error("Failed add network. attempting to cleanup bridge: " + str(e) + ", " + traceback.format_exc())
            try:
                output = corsavfc.bridge_delete(headers, url_switch, str(c_br))
            except Exception as e2:
                LOG.error(" Failed to cleanup bridge after failed add_network: " + str(segmentation_id) + ", bridge: " + str(bridge) + ", Error: " + str(e2))
            raise e


    def add_network_to_existing_vfc(self, segmentation_id, network_id, bridge, vfc_name, of_controller=None):
        token = self.config['token']
        headers = {'Authorization': token}

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr

        c_vlan = segmentation_id
        c_uplink_ports = self.config['uplink_ports']

        c_vfc_name = vfc_name
        c_br = bridge


        LOG.info("PRUTH: --- add_network_to_existing_vfc: " + str(c_br))

        try:
            with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):

                c_br_descr = corsavfc.get_bridge_descr(headers, url_switch, c_br)
                c_br_descr = c_br_descr + "-" + str(segmentation_id)
                corsavfc.bridge_modify_descr(headers, url_switch , c_br, c_br_descr)

                #if of_controller:
                #    cont_ip, cont_port = of_controller
                #    vfc_controller_ip = self.get_ofcontroller_ip_address(c_br)
                #    LOG.info("PRUTH: --- Controller Specified: " + str(cont_ip))
                #    LOG.info("PRUTH: --- Controller Current  : " + str(vfc_controller_ip))

                #    if vfc_controller_ip != cont_ip:
                #        cont_id = 'CONT' + str(c_br) 
                #        corsavfc.bridge_detach_controller(headers, url_switch, br_id = c_br, cont_id = cont_id)
                #        corsavfc.bridge_add_controller(headers, url_switch, br_id = c_br, cont_id = cont_id, cont_ip = cont_ip, cont_port = cont_port)

                LOG.info("About to get_ofport: c_br: " + str(c_br) + ", c_uplink_ports: " + str(c_uplink_ports))
                for uplink in c_uplink_ports.split(','):
                     #Attach the uplink tunnel
                     LOG.info("About to get_ofport: c_br: " + str(c_br) + ", uplink: " + str(uplink))
                     #The logical port number of an uplink is assumed to be the VLAN id
                     ofport=c_vlan
                     LOG.info("ofport: " + str(ofport))
                     corsavfc.bridge_attach_tunnel_ctag_vlan(headers, url_switch, br_id = c_br, ofport = ofport, port = int(uplink), vlan_id = c_vlan)

        except Exception as e:
            LOG.error("Failed add network. attempting to cleanup bridge: " + str(e) + ", " + traceback.format_exc())
            try:
                output = corsavfc.bridge_delete(headers, url_switch, str(c_br))
            except Exception as e2:
                LOG.error(" Failed to cleanup bridge after failed add_network: " + str(segmentation_id) + ", bridge: " + str(bridge) + ", Error: " + str(e2))
            raise e

    #
    # Special case: 
    # Networks are created on the designated VFC (sharedNonByocVFC)
    # Port numbers are created by using the last 3 digits of VLAN tags (segmenration id)
    # Current vlan-port mapping cannot handle VLAN pools that span thousand range
    # VLAN range can be 3000-3999
    #
    def add_network_to_sharedNonByoc_vfc(self, segmentation_id, network_id):
        token = self.config['token']
        headers = {'Authorization': token}

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr

        c_vlan = segmentation_id
        c_uplink_ports = self.config['uplink_ports']

        c_br = self.config['sharedNonByocVFC']

        isVFCHost = True
        if not 'VFCHost' in self.config or not self.config['VFCHost'] == 'True':
            LOG.info("PRUTH: Skipping VFC Creation: isVFCHost " + str(isVFCHost))
            isVFCHost = False
            return
 

        LOG.info("PRUTH: --- add_network_to_sharedNonByoc_vfc: " + str(c_br))

        try:
            with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):

                LOG.info("About to get_ofport: c_br: " + str(c_br) + ", c_uplink_ports: " + str(c_uplink_ports))
                for uplink in c_uplink_ports.split(','):
                     # Attach the uplink tunnel
                     LOG.info("About to get_ofport: c_br: " + str(c_br) + ", uplink: " + str(uplink))
                     # Logical port number of an uplink port is last 3 digits of VLAN tag
                     ofport=str(c_vlan)[-3:]
                     LOG.info("ofport: " + str(ofport))
                     corsavfc.bridge_attach_tunnel_ctag_vlan(headers, url_switch, br_id = c_br, ofport = int(ofport), port = int(uplink), vlan_id = c_vlan)

        except Exception as e:
            LOG.error("Failed add network. attempting to cleanup bridge: " + str(e) + ", " + traceback.format_exc())
            raise e


    def find_named_vfc(self, vfc_name):
        token = self.config['token']
        headers = {'Authorization': token}

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr

        bridge = None
        try:
          with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):
            bridge = corsavfc.get_bridge_by_vfc_name(headers, url_switch, str(vfc_name))
        except Exception as e:
            LOG.error("failed get bridge by vfc name: " + traceback.format_exc())
            raise e

        return bridge

    
    def get_ofcontroller_ip_address(self, bridge):
        token = self.config['token']
        headers = {'Authorization': token}

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr

        ofcontroller_ip = None
        try:
          with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):
            br_num = bridge.replace(bridge,"")
            ofcontroller = corsavfc.get_bridge_controller(headers, url_switch, bridge_number=br_num)
        except Exception as e:
            LOG.error("failed get ofcontroller ip address: " + traceback.format_exc())
            raise e
        # OF Controllers have the name as CONTbr<N>
        ofcontroller_name = 'CONT' + str(bridge)
        ofcontroller_href = ofcontroller.json()['links'][ofcontroller_name]['href']
        ofcontroller_details = corsavfc.get_info(headers, url_switch, ofcontroller_details)        
        ofcontroller_ip = ofcontroller_details.json().get("ip")
        return ofcontroller_ip



   
    def del_network(self, segmentation_id, project_id):
        token = self.config['token']
        headers = {'Authorization': token}
            
        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr

        sharedNonByocVFC = self.config['sharedNonByocVFC'] 

        isVFCHost = True
        if not 'VFCHost' in self.config or not self.config['VFCHost'] == 'True':
            LOG.info("PRUTH: Skipping VFC Deletion: isVFCHost " + str(isVFCHost))
            isVFCHost = False
            return

        bridge = None
        try:    
          with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):
            bridge = corsavfc.get_bridge_by_segmentation_id(headers, url_switch, str(segmentation_id))
            if not bridge == None:
                LOG.info("PRUTH: del_network - network in ByocVfc: " + str(bridge))
                br_descr = corsavfc.get_bridge_descr(headers, url_switch, bridge)
                # br_descr format: <PROJECT_ID>-<VFC_NAME>-VLAN-<TAG1>-<TAG2>
                VLAN_tags = br_descr.split('-')[3:] 
                if (len(VLAN_tags) > 1):
                    br_descr = br_descr.replace("-" + str(segmentation_id), "")
                    ofport = segmentation_id
                    corsavfc.bridge_modify_descr(headers, url_switch , bridge, br_descr)
                    corsavfc.bridge_detach_tunnel(headers, url_switch, bridge, ofport)
                else: 
                    output = corsavfc.bridge_delete(headers, url_switch, str(bridge))
            else:
                LOG.info("PRUTH: del_network - network in sharedNonByocVfc" )
                ofport = int(str(segmentation_id)[-3:])
                sharedNonByocVfc_tunnel = corsavfc.get_tunnel_by_bridge_and_ofport(headers, url_switch, 
                                                                               sharedNonByocVFC, ofport)
                corsavfc.bridge_detach_tunnel(headers, url_switch, sharedNonByocVFC, int(sharedNonByocVfc_tunnel))
                
        except Exception as e:
            LOG.error("failed delete network : " + traceback.format_exc())
            raise e
    
    # gets the unique ofport based on the bridge number and port number
    # Example: bridge=br3,port=P 32 -> ofport 332
    #          bridge=br33,port=P 2 -> ofport 3302 
    def get_ofport(self, bridge, port):
        #return port from mapping

        ofport = bridge[2:]
        if int(port[2:]) < 10:
            ofport += '0'
        ofport += port[2:]

        return ofport


    def get_sharedNonByocPort(self, port, segmentation_id):
        #sharedNonByocVLAN = self.config['sharedNonByocVLAN']
        port_num=port[2:]
        segmentation_id_first_digit = str(segmentation_id)[0]
        segmentation_id_last3_digit = str(segmentation_id)[-3:]
        ofport = port_num + segmentation_id_last3_digit
        return int(ofport)



    def plug_port_to_network(self, port, segmentation_id, vfc_host):
        #OpenStack requires port ids to not be numbers
        #Corsa uses numbers
        #We are lying to OpenStack by adding a 'p ' to the beging of each port number.
        #We need to strip the 'p ' off of the port number.
        port_num=port[2:]
        
        # 
        # REST calls should be sent to the vfc_host for both corsa switch instances 
        # 
        token = vfc_host.config['token']
        headers = {'Authorization': token}

        protocol = 'https://'
        sw_ip_addr = vfc_host.config['switchIP']
        url_switch = protocol + sw_ip_addr
        sharedNonByocVFC = self.config['sharedNonByocVFC']

        LOG.info("PRUTH: plug_port_to_network - switch: " + str(self) + ",  switch: " + self.config['name'] ) 
        LOG.info("PRUTH: plug_port_to_network - self.config: " + str(self.config))
        LOG.info("PRUTH: plug_port_to_network - Binding port " + str(port) + " to network " + str(segmentation_id))

        ofport=None
        node_vlan=None
        dst_switch_name=None

        try:    
            with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):
                # search segmentation id in BYOC VFCs
                byocVFC = corsavfc.get_bridge_by_segmentation_id(headers, url_switch, str(segmentation_id))
                if not byocVFC == None:
                    br_id = byocVFC
                else:
                    uplink_ofport = int(str(segmentation_id)[-3:])
                    sharedNonByocVfc_tunnel = corsavfc.get_tunnel_by_bridge_and_ofport(headers, url_switch, sharedNonByocVFC, uplink_ofport)
                    if str(uplink_ofport) == str(sharedNonByocVfc_tunnel): 
                        br_id = sharedNonByocVFC
                    else:
                        LOG.info("PRUTH: plug_port_to_network - Network missing in sharedNonByocVFC")
 
                LOG.info("PRUTH: plug_port_to_network - br_id : " + str(br_id) + " for network " + str(segmentation_id))
      
                if port in self.config:
                    LOG.info("PRUTH: plug_port_to_network - Binding port " + str(port) + " maps to " + str(self.config[port]))
                    if br_id == sharedNonByocVFC:
                        ofport = self.get_sharedNonByocPort(port, segmentation_id)   
                        if not vfc_host == self:
                            p = str(ofport)[:-3]
                            v = str(ofport)[-3:]
                            p_num = int(p) + 32
                            ofport = int(str(p_num) + v)
                        LOG.info("PRUTH: plug_port_to_network - sharedNonByocVFC: " + str(br_id) + " ofport: " + str(ofport))
                    else:
                        ofport=str(int(self.config[port])+10000)
                        LOG.info("PRUTH: plug_port_to_network - ByocVFC: " + str(br_id) + " ofport: " + str(ofport))

                    node_vlan=self.config[port]

                else:
                    LOG.info("PRUTH: plug_port_to_network - Binding port " + str(port) +" missing")
                    LOG.info("PRUTH: plug_port_to_network - Binding port " + str(self.config))

                if 'name' in self.config:
                    dst_switch_name=self.config['name']
                    LOG.info("PRUTH: plug_port_to_network - dst_switch_name " + str(dst_switch_name))

                if not vfc_host == self:
                    #Step 1: config local switch
                    #For now, VLANs are staticlly configured so this is a no-op

                    #Step 2: config VFCHost with ctag tunnel
                    #params:  segmentaion_id, node_vlan, destination_switch_name
                    vfc_host.__bind_ctag_tunnel(segmentation_id, node_vlan, dst_switch_name, ofport)
                    
                else: 
                    #Step 2: config VFCHost (i.e. local host) with passthrough tunnel
                    self.__bind_passthrough_tunnel(port, segmentation_id, ofport)

        except Exception as e:
            LOG.error("failed plug_port_to_network : " + traceback.format_exc())
            raise e
    
    def __bind_passthrough_tunnel(self, port, segmentation_id, ofport):
        port_num=port[2:]
        token = self.config['token']
        headers = {'Authorization': token}

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr
        sharedNonByocVFC = self.config['sharedNonByocVFC']

        corsavfc.port_modify_tunnel_mode(headers, url_switch, port_num, 'passthrough')

        # get the bridge from segmentation_id                   
        byocVFC = corsavfc.get_bridge_by_segmentation_id(headers, url_switch, str(segmentation_id))
        if not byocVFC == None:
            br_id = byocVFC
        else:
            br_id = sharedNonByocVFC

        LOG.info("PRUTH: __bind_passthrough_tunnel - br_id: " + str(br_id) + " segmentation_id: " + str(segmentation_id)
                                                      + " port_num: " + str(port_num) + " ofport: " + str(ofport) )
        corsavfc.bridge_attach_tunnel_passthrough(headers, url_switch, br_id, port_num, ofport, tc = None, descr = None, shaped_rate = None)




    def __bind_ctag_tunnel(self, segmentation_id, node_vlan, dst_switch_name, ofport=None):
        LOG.info("PRUTH: __bind_ctag_tunnel - adding to vfc_host: __bind_ctag_tunnel")      
        LOG.info("PRUTH: __bind_ctag_tunnel - switch: " + self.config['name'] + ", VFCHost: " + str(segmentation_id) + ", " + str(node_vlan) + ", " + str(dst_switch_name))

        #port_num=port[2:]
        token = self.config['token']
        headers = {'Authorization': token}

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr
        sharedNonByocVFC = self.config['sharedNonByocVFC']
        
        dst_port=None
        if dst_switch_name in self.config:
            dst_port=self.config[dst_switch_name]

        LOG.info("PRUTH: __bind_ctag_tunnel - About to dst_port: " + str(dst_port) )
        byocVFC = corsavfc.get_bridge_by_segmentation_id(headers, url_switch, segmentation_id)
        if not byocVFC == None:
            br_id = byocVFC
        else:
            br_id = sharedNonByocVFC

        if not ofport:
            ofport=str(int(str(node_vlan))+10000)
        LOG.info("PRUTH: __bind_ctag_tunnel - ofport: " + str(ofport))
        LOG.info("PRUTH: __bind_ctag_tunnel - br_id : " + str(br_id))
        corsavfc.bridge_attach_tunnel_ctag_vlan(headers, url_switch, br_id = br_id, ofport = ofport, port = int(dst_port), vlan_id = node_vlan)


    def delete_port(self, port, segmentation_id, vfc_host, ofport=None):

        # 
        # REST calls should be sent to the vfc_host for both corsa switch instances 
        # 
        token = vfc_host.config['token']
        headers = {'Authorization': token}

        protocol = 'https://'
        sw_ip_addr = vfc_host.config['switchIP']
        url_switch = protocol + sw_ip_addr
        sharedNonByocVFC = self.config['sharedNonByocVFC']


        byocVFC = corsavfc.get_bridge_by_segmentation_id(headers, url_switch, segmentation_id)
        if not byocVFC == None:
             br_id = byocVFC
        else:
            br_id = sharedNonByocVFC
        LOG.info("PRUTH: delete_port - br_id on VFCHost: " + str(br_id) + " for network " + str(segmentation_id))

        if ofport == None and port in self.config:
            LOG.info("PRUTH: delete_port - port: " + str(port) + " maps to " + str(self.config[port]))
            if br_id == sharedNonByocVFC:
                ofport = self.get_sharedNonByocPort(port, segmentation_id)
                if not vfc_host == self:
                    p = str(ofport)[:-3]
                    v = str(ofport)[-3:]
                    p_num = int(p) + 32
                    ofport = int(str(p_num) + v)
                LOG.info("PRUTH: delete_port - sharedNonByocVFC: " + str(br_id) + " ofport: " + str(ofport))
            else:   
                ofport=str(int(self.config[port])+10000)
                LOG.info("PRUTH: delete_port - ByocVFC: " + str(br_id) + " ofport: " + str(ofport))
        if not vfc_host == self:
            vfc_host.delete_port(port, segmentation_id, vfc_host, ofport=ofport)
        else:
            self.__delete_ofport(ofport, segmentation_id)



    def __delete_ofport(self, ofport, segmentation_id):
        # OpenStack requires port ids to not be numbers
        # Corsa uses numbers
        # We are lying to OpenStack by adding a 'p ' to the beging of each port number.
        # We need to strip the 'p ' off of the port number. 
        # port_num=port[2:]

        token = self.config['token']
        headers = {'Authorization': token}

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr
        sharedNonByocVFC = self.config['sharedNonByocVFC']

        LOG.info("PRUTH: delete port: switch: " + self.config['name'] + ", ofport: " + str(ofport) + ", segmentation_id: " + str(segmentation_id))

        try:
          with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):
            # get the bridge from segmentation_id
            byocVFC = corsavfc.get_bridge_by_segmentation_id(headers, url_switch, segmentation_id)
            if not byocVFC == None:
                br_id = byocVFC
            else:
                br_id = sharedNonByocVFC    

            # unbind the port
            # openflow port was mapped to the physical port with the same port number in plug_port_to_network
            #ofport = self.get_ofport(br_id,port)
            corsavfc.bridge_detach_tunnel(headers, url_switch, br_id, ofport)

        except Exception as e:
            LOG.error("Failed delete_port: " + traceback.format_exc())
            raise e



    def __delete_port(self, port, segmentation_id):
        # OpenStack requires port ids to not be numbers       
        # Corsa uses numbers 
        # We are lying to OpenStack by adding a 'p ' to the beging of each port number.
        # We need to strip the 'p ' off of the port number.      
        port_num=port[2:]

        token = self.config['token']
        headers = {'Authorization': token}

        logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)

        protocol = 'https://'
        sw_ip_addr = self.config['switchIP']
        url_switch = protocol + sw_ip_addr
        sharedNonByocVFC = self.config['sharedNonByocVFC']

        LOG.info("PRUTH: delete port: switch: " + self.config['name'] + ", port: " + str(port) + ", segmentation_id: " + str(segmentation_id))

        ofport=None
        if port in self.config:
            LOG.info("PRUTH: delete port " + str(port) + " maps to " + str(self.config[port]))
            ofport=str(int(self.config[port])+10000)

        try:
          with ngs_lock.PoolLock(self.locker, **self.lock_kwargs):
            # get the bridge from segmentation_id
            byocVFC = corsavfc.get_bridge_by_segmentation_id(headers, url_switch, segmentation_id)
            if not byocVFC == None:
                br_id = byocVFC
            else:
                br_id = sharedNonByocVFC    

            # unbind the port 
            # openflow port was mapped to the physical port with the same port number in plug_port_to_network
            #ofport = self.get_ofport(br_id,port)
            corsavfc.bridge_detach_tunnel(headers, url_switch, br_id, ofport)
 
        except Exception as e:
            LOG.error("Failed delete_port: " + traceback.format_exc())
            raise e

