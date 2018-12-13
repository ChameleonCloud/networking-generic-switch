#!/usr/bin/env python 

from oslo_log import log as logging
import requests
import json
import re

LOG = logging.getLogger(__name__)

#
# ENDPOINTS
#
endpoint = '/api/v1'
ep_datapath = endpoint + '/datapath'    # Datapath
ep_bridges = endpoint + '/bridges'      # Bridge
ep_stats = endpoint + '/stats'          # Stats
ep_users = endpoint + '/users'          # Users
ep_system = endpoint + '/system'        # System
ep_equipment = endpoint + '/equipment'  # Equipment
ep_tunnels = endpoint + '/tunnels'      # Tunnels
ep_qp = endpoint + '/queue-profiles'    # Queue-profiles        
ep_ports = endpoint + '/ports'          # Ports
ep_containers = endpoint + '/containers'# Containers
ep_netns = endpoint + '/netns'



#
# PORT MODIFY
#
#   204 No content
#   400 Bad Request
#   403 Forbidden
#   404 Not Found
#   409 Conflict 


def port_modify_tunnel_mode(headers, url_switch , port_number, tunnel_mode):
    url = url_switch + ep_ports + '/' + str(port_number)
    data = [
              { "op": "replace", "path": "/tunnel-mode", "value": tunnel_mode },
           ]
    try:
        r = requests.patch(url, data=json.dumps(data), headers=headers, verify=False)
    except Exception as e:
        raise e
    return r
 
  
def port_modify_mtu(headers, url_switch , port_number, mtu):
    url = url_switch + ep_ports + '/' + str(port_number)
    data = [
              { "op": "replace", "path": "/mtu", "value": mtu },
           ]
    try:
        r = requests.patch(url, data=json.dumps(data), headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


def port_modify_descr(headers, url_switch , port_number, descr):
    url = url_switch + ep_ports + '/' + str(port_number)
    data = [
              { "op": "replace", "path": "/ifdescr", "value": descr },
           ]
    try:
        r = requests.patch(url, data=json.dumps(data), headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


def port_modify_bandwidth(headers, url_switch , port_number, bandwidth):
    url = url_switch + ep_ports + '/' + str(port_number)
    data = [
              { "op": "replace", "path": "/bandwidth", "value": bandwidth },
           ]
    try:
        r = requests.patch(url, data=json.dumps(data), headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


def port_modify_admin_state(headers, url_switch , port_number, admin_state):
    url = url_switch + ep_ports + '/' + str(port_number)
    data = [
              { "op": "replace", "path": "/admin-state", "value": admin_state },
           ]
    try:
        r = requests.patch(url, data=json.dumps(data), headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


def bridge_modify_descr(headers, url_switch , bridge, br_descr):
    url = url_switch + ep_bridges + '/' + str(bridge)
    data = [
              { "op": "replace", "path": "/bridge-descr", "value": br_descr },
           ]
    try:
        r = requests.patch(url, data=json.dumps(data), headers=headers, verify=False)
    except Exception as e:
        raise e
    return r





#
# BRIDGE CREATE
#
#   201 Created
#   400 Bad Request
#   403 Forbidden
#   409 Conflict

def bridge_create(headers, 
                  url_switch, 
                  br_id, 
                  br_dpid = None, 
                  br_subtype = None, 
                  br_resources = None, 
                  br_traffic_class = None, 
                  br_descr = None,
                  br_namespace = None): 
    url = url_switch + ep_bridges
    data = {
        'bridge':br_id,
        'subtype':br_subtype,
        'resources': br_resources,
        'dpid': br_dpid,
        'traffic-class': br_traffic_class,
        'bridge-descr': br_descr,
        'netns': br_namespace
    }

    try:
        output = requests.post(url ,data=data, headers=headers, verify=False)

        if output.status_code == 201:
            LOG.info(" Create Bridge: " + "url: " + str(url) + ", " + str(output.status_code) + " Success")
        else:
            if output.status_code == 400:
                raise Exception(" Create Bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Bad Request")
            elif output.status_code == 403:
                raise Exception(" Create Bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Forbidden")
            elif output.status_code == 409:
                raise Exception(" Create Bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Conflict")
            else:
                raise Exception(" Create Bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Unknown Error")


    except Exception as e:
        raise e
    return output


#
# BRIDGE DELETE
#
#   200 OK   PRUTH: I think its actually 204
#   403 Forbidden
#   404 Not found

def bridge_delete(headers,
                  url_switch,
                  br_id):
    url = url_switch + ep_bridges + '/' +  br_id 

    try:
        output = requests.delete(url, headers=headers, verify=False)

        if output.status_code == 204:
            LOG.info(" Delete Bridge: " + "url: " + str(url) + ", " + str(output.status_code) + " Success")
        else:
            if output.status_code == 403:
                raise Exception(" Delete Bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Forbidden")
            elif output.status_code == 404:
                raise Exception(" Delete Bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Not Found")
            else:
                raise Exception(" Delete Bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Unknown Error")

    except Exception as e:
        raise e
    return output


#
# ADD CONTROLLER
#
#   201 Created
#   400 Bad Request
#   403 Forbidden
#   404 Not Found
#   409 Conflict

def bridge_add_controller(headers,
                         url_switch,
                         br_id, 
                         cont_id,
                         cont_ip,
                         cont_port, 
                         cont_tls = False):
    url = url_switch + ep_bridges + '/' + br_id + '/controllers'
    data = {
             'controller':cont_id,
             'ip':cont_ip,
             'port': cont_port,
             'tls': cont_tls
           }

    try:
        output = requests.post(url ,data=data, headers=headers, verify=False)

        if output.status_code == 201:
            LOG.info(" Add Controller: url: " + str(url)  + ", " + str(output.status_code) + " Success")
        else:
            if output.status_code == 400:
                raise Exception(" Add Controller Failed:  url: " + str(url)  + ", "  + str(output.status_code) + " Bad Request")
            elif output.status_code == 403:
                raise Exception(" Add Controller Failed:  url: " + str(url)  + ", "  + str(output.status_code) + " Forbidden")
            elif output.status_code == 404:
                raise Exception(" Add Controller Failed:  url: " + str(url)  + ", "  + str(output.status_code) + " Not Found")
            else:
                raise Exception(" Add Controller Failed:  url: " + str(url)  + ", "  + str(output.status_code) + " Unknown Error")

    except Exception as e:
        raise e
    return output


#
# DETACH CONTROLLER
#
#   204 No Content
#   403 Forbidden
#   404 Not Found

def bridge_detach_controller(headers,
                             url_switch,
                             br_id,
                             cont_id):
    url = url_switch + ep_bridges + '/' +  br_id + '/controllers' + '/' + cont_id

    try:
        output = requests.delete(url, headers=headers, verify=False)
        if output.status_code == 204:
            LOG.info(" Add Controller: " + "url: " + str(url) + ", " + str(output.status_code) + " Success")
        else:
            if output.status_code == 400:
                raise Exception(" Add Controller Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Bad Request")
            elif output.status_code == 403:
                raise Exception(" Add Controller Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Forbidden")
            elif output.status_code == 404:
                raise Exception(" Add Controller Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Not Found")
            elif output.status_code == 409:
                raise Exception(" Add Controller Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Conflict")
            else:
                raise Exception(" Add Controller Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Unknown Error")

    except Exception as e:
        raise e
    return r


#
# ATTACH TUNNEL - VLAN ID
#
#   201 Created
#   400 Bad Request
#   403 Forbidden
#   404 Not Found

def bridge_attach_tunnel_ctag_vlan(headers,
                                   url_switch,
                                   br_id, 
                                   ofport,
                                   port,
                                   vlan_id,
                                   tc = None,
                                   descr = None,
                                   shaped_rate = None):
    url = url_switch + ep_bridges + '/' +  br_id + '/tunnels'
    data = {
             'ofport': ofport,
             'port': port,
             'vlan-id': vlan_id,
             'traffic-class': tc,
             'ifdescr': descr,
             'shaped-rate': shaped_rate,
           }

    try:
        output = requests.post(url ,data=data, headers=headers, verify=False)

        if output.status_code == 201:
                LOG.info(" Attach ctag vlan port to bridge: " + "url: " + str(url) + ", " + str(output.status_code) + " Success")
        else:
            if output.status_code == 400:
                raise Exception(" Attach ctag vlan port to bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Bad Request")
            elif output.status_code == 403:
                raise Exception(" Attach ctag vlan port to bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Forbidden")
            elif output.status_code == 404:
                raise Exception(" Attach ctag vlan port to bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Not Found")
            else:
                raise Exception(" Attach ctag vlan port to bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Unknown Error")

    except Exception as e:
        reclaim_ofport(headers, url_switch, ofport)
        raise e
    return output


#
# ATTACH TUNNEL - PASSTHROUGH
#
#   201 Created
#   400 Bad Request
#   403 Forbidden  
#   404 Not Found 

def bridge_attach_tunnel_passthrough(headers,
                                     url_switch,
                                     br_id,
                                     port,
                                     ofport = None,
                                     tc = None,
                                     descr = None,
                                     shaped_rate = None):
    url = url_switch + ep_bridges +  '/' +  str(br_id) + '/tunnels'
    data = {
             'ofport': ofport,
             'port': port,
             'traffic-class': tc,
             'ifdescr': descr,
             'shaped-rate': shaped_rate,
           }

    LOG.info(" Attach passthrough port to bridge: port: " + str(port) + ", ofport = " + str(ofport))

    try:
        output = requests.post(url ,data=data, headers=headers, verify=False)

        if output.status_code == 201:
            LOG.info(" Attach passthrough port to bridge: " + "url: " + str(url) + ", " + str(output.status_code) + " Success")
        else:
            if output.status_code == 400:
                raise Exception(" Attach passthrough port to bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Bad Request")
            elif output.status_code == 403:
                reclaim_port(headers,url_switch,port)
                raise Exception(" Attach passthrough port to bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Forbidden")
            elif output.status_code == 404:
                raise Exception(" Attach passthrough port to bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Not Found")
            else:
                raise Exception(" Attach passthrough port to bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Unknown Error")


    except Exception as e:
        raise e
    return output

#public facing function that tries to clean up and retry once on failure
#def bridge_attach_tunnel_passthrough(headers,
#                                     url_switch,
#                                     br_id,
#                                     port,
#                                     ofport = None,
#                                     tc = None,
#                                     descr = None,
#                                     shaped_rate = None):
#   
#    try:
#        __bridge_attach_tunnel_passthrough(headers, url_switch, br_id, port, ofport, tc, descr, shaped_rate)
#    except Exception as e:
#        reclaim_port(headers,url_switch,port)
#        __bridge_attach_tunnel_passthrough(headers, url_switch, br_id, port, ofport, tc, descr, shaped_rate)
     

#
# ATTACH TUNNEL - VLAN RANGE
#
#   201 Created
#   400 Bad Request
#   403 Forbidden
#   404 Not Found

def bridge_attach_tunnel_ctag_vlan_range(headers,
                                         url_switch,
                                         br_id, 
                                         ofport,
                                         port,
                                         vlan_range,
                                         tc = None,
                                         descr = None,
                                         shaped_rate = None):
    url = url_switch + ep_bridges +  '/' +  br_id + '/tunnels'
    data = {
             'ofport': ofport,
             'port': port,
             'vlan-range': vlan_range,
             'traffic-class': tc,
             'ifdescr': descr,
             'shaped-rate': shaped_rate,
           }

    try:
        r = requests.post(url ,data=data, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# DETACH TUNNEL
#
#   204 No content
#   403 Forbidden
#   404 Not Found

def bridge_detach_tunnel(headers,
                         url_switch,
                         br_id,
                         ofport):
    url = url_switch + ep_bridges + '/' +  str(br_id) + '/tunnels' + '/' + str(ofport)

    try:
        output = requests.delete(url, headers=headers, verify=False)
        if output.status_code == 204:
            LOG.info(" Detach port from bridge: " + "url: " + str(url) + ", " + str(output.status_code) + " Success")
        else:
            if output.status_code == 400:
                raise Exception(" Detach port from bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Bad Request")
            elif output.status_code == 403:
                raise Exception(" Detach port from bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Forbidden")
            elif output.status_code == 404:
                raise Exception(" Detach port from bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Not Found")
            else:
                raise Exception(" Detach port from bridge Failed: " + "url: " + str(url) + ", " + str(output.status_code) + " Unknown Error")


    except Exception as e:
        raise e
    return output


#
# GET DATAPATH
#
#   200 OK
#   303 See Other
def get_datapath(headers,
                 url_switch):
    url = url_switch + ep_datapath

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET DATAPATH LAG-HASH
#
#   200 OK
def get_datapath_laghash(headers,
                         url_switch):
    url = url_switch + ep_datapath + '/lag-hash'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET DATAPATH STATUS
#
#   200 OK
#   303 See other
def get_datapath_status(headers,
                        url_switch):
    url = url_switch + ep_datapath + '/status'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT
#
#   200 OK
#
def get_equipment(headers,
                  url_switch):
    url = url_switch + ep_equipment

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT SLOTS
#
#   200 OK
#
def get_equipment_slots(headers,
                        url_switch):
    url = url_switch + ep_equipment + '/slots'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT SLOT 
#
#   200 OK
#
def get_equipment_slot(headers,
                       url_switch,
                       slot):
    url = url_switch + ep_equipment + '/slots/' + str(slot)

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT SLOT MODULE 
#
#   200 OK
#   404 Not Found
def get_equipment_slot_module(headers,
                              url_switch,
                              slot):
    url = url_switch + ep_equipment + '/slots/' + str(slot) + '/module'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT FANTRAYS
#
#   200 OK
#
def get_equipment_fantrays(headers,
                           url_switch):
    url = url_switch + ep_equipment + '/fantrays'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT FANTRAY
#
#   200 OK
#   404 Not Found
def get_equipment_fantray(headers,
                          url_switch,
                          fantray):
    url = url_switch + ep_equipment + '/fantrays/' + str(fantray)

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT FANS
#
#   200 OK
#   404 Not Found
def get_equipment_fans(headers,
                       url_switch,
                       fantray):
    url = url_switch + ep_equipment + '/fantrays/' + str(fantray) + '/fans'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r



#
# GET EQUIPMENT FAN
#
#   200 OK
#   404 Not Found
def get_equipment_fan(headers,
                      url_switch,
                      fantray,
                      fan):
    url = url_switch + ep_equipment + '/fantrays/' + str(fantray) + '/fans/' + str(fan)

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT LED
#
#   200 OK
#
def get_equipment_led(headers,
                      url_switch):
    url = url_switch + ep_equipment + '/led'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT BOARDTEMP
#
#   200 OK
#
def get_equipment_boardtemp(headers,
                            url_switch):
    url = url_switch + ep_equipment + '/boardtemp'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT CPU
#
#   200 OK
#
def get_equipment_cpu(headers,
                      url_switch):
    url = url_switch + ep_equipment + '/cpu'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT PSUS
#
#   200 OK
#
def get_equipment_psus(headers,
                       url_switch):
    url = url_switch + ep_equipment + '/psus'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT PSU
#
#   200 OK
#
def get_equipment_psu(headers,
                      url_switch,
                      psu):
    url = url_switch + ep_equipment + '/psus/' + str(psu)

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT EEPROMS
#
#   200 OK
#
def get_equipment_eeproms(headers,
                          url_switch):
    url = url_switch + ep_equipment + '/eeproms'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT EEPROM
#
#   200 OK
#
def get_equipment_eeprom(headers,
                         url_switch,
                         eeprom):
    url = url_switch + ep_equipment + '/eeproms/' + str(eeprom)

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET EQUIPMENT AIRFLOW
#
#   200 OK
#
def get_equipment_airflow(headers,
                          url_switch):
    url = url_switch + ep_equipment + '/airflow'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET NETNS
#
#   200 OK
#
def get_netns_info(headers,
                   url_switch):
    url = url_switch + ep_netns 

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET NETNS SPECIFIC
#
#   200 OK
#
def get_netns(headers,
              url_switch,
              netns):
    url = url_switch + ep_netns + '/' + str(netns)

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET NETNS TUNNELS
#
#   200 OK
#
def get_netns_tunnels(headers,
                      url_switch,
                      netns):
    url = url_switch + ep_netns + '/' + str(netns) + '/tunnels'

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET NETNS TUNNEL
#
#   200 OK
#
def get_netns_tunnel(headers,
                     url_switch,
                     netns,
                     tunnel):
    url = url_switch + ep_netns + '/' + str(netns) + '/tunnels/' + str(tunnel)

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET PORTS
#
#   200 OK
#   403 Forbidden
def get_ports(headers,
              url_switch):
    url = url_switch + ep_ports

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET PORT
#
#   200 OK
#   403 Forbidden
def get_port(headers,
             url_switch,
             port):
    url = url_switch + ep_ports + '/' + str(port)

    try: 
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET PORT TRAFFIC CLASSES
#
#   200 OK
#   403 Forbidden
def get_port_traffic_class(headers,
                           url_switch,
                           port):
    url = url_switch + ep_ports + '/' + str(port) + '/traffic-classes'

    try: 
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET QUEUE PROFILES
#
#   200 OK
#   
def get_queue_profiles(headers,
                       url_switch):
    url = url_switch + ep_qp

    try: 
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r



#
# GET STATS
#
#   200 OK
#   
def get_stats(headers,
              url_switch):
    url = url_switch + ep_stats

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET STATS PORTS
#
#   200 OK
#   
def get_stats_ports(headers,
                    url_switch,
                    port=None):
    if port:
        url = url_switch + ep_stats + '/ports?port=' + str(port)
    else:
        url = url_switch + ep_stats + '/ports'

    try: 
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET STATS TUNNELS
#
#   200 OK
#   
def get_stats_tunnels(headers,
                      url_switch,
                      bridge=None,
                      ofport=None):
    if bridge and ofport: 
        url = url_switch + ep_stats + '/tunnels' + '?bridge=br' + str(bridge) + '&ofport=' + str(ofport)
    elif bridge and not ofport:
        url = url_switch + ep_stats + '/tunnels' + '?bridge=br' + str(bridge)
    else:
        url = url_switch + ep_stats + '/tunnels'

    try: 
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET SYSTEM
#
#   200 OK
#   
def get_system(headers,
               url_switch):
    url = url_switch + ep_system

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET TUNNELS
#
#   200 OK
#   
def get_tunnels(headers,
                url_switch,
                qlist=None):
    if qlist:
        url = url_switch + ep_tunnels + '?list=true'
    else:
        url = url_switch + ep_tunnels 

    try: 
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r









#
# GET BRIDGES
#
#   200
#   403 Forbidden
def get_bridges(headers,
                url_switch):
    url = url_switch + ep_bridges

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET BRIDGE
#
#   200     
#   403 Forbidden
def get_bridge(headers,
                url_switch,
                bridge_url):
    
    try:
        r = requests.get(bridge_url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r

#
# GET BRIDGE WITH BR NUMBER
#
#   200     
#   403 Forbidden
def get_bridge_by_number(headers,
                         url_switch,
                         bridge_number):

    url = url_switch + ep_bridges + '/' + 'br' + str(bridge_number)

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r


#
# GET CONTROLLER
#
#   200     
#   403 Forbidden
#   404 Not Found
def get_bridge_controller(headers,
                          url_switch,
                          bridge_number=None,
                          bridge_url=None):

    if bridge_number and not bridge_url:
        url = url_switch + ep_bridges + '/br' + str(bridge_number) + '/controllers'
    elif bridge_url and not bridge_number:
        url = bridge_url + '/controllers'
    else:
        return 404       

    try:
        r = requests.get(url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r




#
# GET INFO
#
#   200
#   403 Forbidden
def get_info(headers,
             url_switch,
             info_url):

    try:
        r = requests.get(info_url, headers=headers, verify=False)
    except Exception as e:
        raise e
    return r



#
# 
#
# get_free_bridge_name
#
#
def get_free_bridge(headers,
                    url_switch):

    bridges = get_bridges(headers,url_switch)

    links=bridges.json()["links"]
    for i in range(1,64):
        bridge = 'br'+str(i)
        if bridge in links.keys():
            continue
        return bridge

    return None

#
# 
#
# get_bridge_by_segmentation_id
#
# By convention we are putting the segmentation_id in the "bridge-description" field
#
def get_bridge_by_segmentation_id(headers,
                                  url_switch,
                                  segmentation_id):
    bridges = get_bridges(headers,url_switch)

    links=bridges.json()["links"]
    for bridge,value in links.items():
        url=value['href']
        link = get_bridge(headers,url_switch,url).json()
        if "bridge-descr" in link.keys():
            bridge_descr = str(link["bridge-descr"])
            # Chameleon specific br_descr format: <PROJECT_ID>-<VFC_NAME>-VLAN-<TAG1>-<TAG2>
            # Extract VLAN tags 
            vlan_tags = re.match( r'(.*?)-(.*?)-VLAN-(.*)', bridge_descr, re.I ) 
            if vlan_tags.group(3) and ( vlan_tags.group(3).find(str(segmentation_id)) > -1 ) :
                return bridge 
    return None


#
# 
#
# get_bridge_by_vfc_name
#
# By convention we are putting the vfc_name in the "bridge-description" field
#
def get_bridge_by_vfc_name(headers,
                           url_switch,
                           vfc_name):
    bridges = get_bridges(headers,url_switch)

    links=bridges.json()["links"]
    for bridge,value in links.items():
        url=value['href']
        link = get_bridge(headers,url_switch,url).json()
        if "bridge-descr" in link.keys():
            bridge_descr=str(link["bridge-descr"])
            if bridge_descr.find(vfc_name) > -1 :
                return bridge
    return None


#
# 
#
# get_bridge_descr
#
# 
#

def get_bridge_descr(headers,
                     url_switch,
                     br_id):
    bridge_url = url_switch + ep_bridges + '/' +  str(br_id) 
    
    bridge = get_bridge(headers, url_switch, bridge_url)
    bridge_descr = bridge.json()["bridge-descr"]
    return bridge_descr

    




#
# reclaim ofport
#
#
def reclaim_ofport(headers,
                 url_switch,
                 ofport):

    bridges = get_bridges(headers,url_switch)

    links=bridges.json()["links"]
    LOG.info("PRUTH: bridges: " + str(links))
    for bridge,value in links.items():
        #bridge = 'br'+str(i)                                                                                                                                                                                                                                    
        #bridgeInfo = get_bridge(headers,url_switch,bridges[bridge])                                                                                                                                                                                             
        #link=links[str(bridge)]                                                                                                                                                                                                                                 
        LOG.info("PRUTH: bridge: " + str(bridge) + ", value: " + str(value )  )
        url=value['href']
        LOG.info("PRUTH: bridge url: " + str(bridge) + ", href: " + str(url)  )
        bridge_data = get_bridge(headers,url_switch,url)
        bridge_tunnels_url = str(bridge_data.json()['links']['tunnels']['href'])
        LOG.info("PRUTH: bridge tunnels url: " + str(bridge_tunnels_url))
        bridge_tunnels = get_info(headers,url_switch,bridge_tunnels_url)
        LOG.info("PRUTH: bridge tunnels: " + str(bridge_tunnels.json()))
        for tunnel,value in bridge_tunnels.json()['links'].items():
            LOG.info("PRUTH: bridge tunnel: " + str(tunnel) + ", value: " + str(value))
            tunnel_url=value['href']
            LOG.info("PRUTH: bridge tunnel_url: " + str(tunnel_url))
            tunnel_info = get_info(headers,url_switch,tunnel_url)
            LOG.info("PRUTH: bridge tunnel_info: " + str(tunnel_info.json()))
            current_port = tunnel_info.json()['port']
            current_ofport = tunnel_info.json()['ofport']
            LOG.info("PRUTH: current_port: " + str(current_port) + ", ofport: " +  str(ofport)  +    ", current_ofport: " + str(current_ofport))
            if str(current_ofport) == str(ofport):
                LOG.info("PRUTH: FOUND PORT. KILL IT. ")
                bridge_detach_tunnel(headers, url_switch, str(bridge), str(current_ofport))

    return None



#
#
#
# reclaim physical port. 
# If we try to bind a port to a VFC and get a "forbidden" return code this could mean 
# that the port is already bound.  In this case we can try to reclaim to port by 
# checking all VFCs for the port and then unbinding it if the port is found.
#
def reclaim_port(headers,
                 url_switch,
                 port):

    bridges = get_bridges(headers,url_switch)

    links=bridges.json()["links"]
    LOG.info("PRUTH: bridges: " + str(links))
    for bridge,value in links.items():
        #bridge = 'br'+str(i)
        #bridgeInfo = get_bridge(headers,url_switch,bridges[bridge])
        #link=links[str(bridge)]
        LOG.info("PRUTH: bridge: " + str(bridge) + ", value: " + str(value )  )
        url=value['href']
        LOG.info("PRUTH: bridge url: " + str(bridge) + ", href: " + str(url)  )
        bridge_data = get_bridge(headers,url_switch,url)
        bridge_tunnels_url = str(bridge_data.json()['links']['tunnels']['href'])
        LOG.info("PRUTH: bridge tunnels url: " + str(bridge_tunnels_url))
        bridge_tunnels = get_info(headers,url_switch,bridge_tunnels_url)
        LOG.info("PRUTH: bridge tunnels: " + str(bridge_tunnels.json()))
        for tunnel,value in bridge_tunnels.json()['links'].items():
            LOG.info("PRUTH: bridge tunnel: " + str(tunnel) + ", value: " + str(value))
            tunnel_url=value['href']
            LOG.info("PRUTH: bridge tunnel_url: " + str(tunnel_url))
            tunnel_info = get_info(headers,url_switch,tunnel_url)
            LOG.info("PRUTH: bridge tunnel_info: " + str(tunnel_info.json()))
            current_port = tunnel_info.json()['port']
            current_ofport = tunnel_info.json()['ofport']
            LOG.info("PRUTH: current_port: " + str(current_port) + ", port: " +  str(port) + ", current_ofport: " + str(current_ofport)) 
            if current_port == port:
                LOG.info("PRUTH: FOUND PORT. KILL IT. ")
                bridge_detach_tunnel(headers, url_switch, str(bridge), str(current_ofport))

    return None




