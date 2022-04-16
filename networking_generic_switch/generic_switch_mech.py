# Copyright 2015 Mirantis, Inc.
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

from neutron.db import provisioning_blocks
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import resources
from neutron_lib.plugins.ml2 import api
from oslo_log import log as logging
from oslo_config import cfg
import socket
import re

from networking_generic_switch import config as gsw_conf
from networking_generic_switch import devices
from networking_generic_switch.devices import utils as device_utils


LOG = logging.getLogger(__name__)

GENERIC_SWITCH_ENTITY = 'GENERICSWITCH'

CONF = cfg.CONF

class GenericSwitchDriver(api.MechanismDriver):

    def initialize(self):
        """Perform driver initialization.

        Called after all drivers have been loaded and the database has
        been initialized. No abstract methods defined below will be
        called prior to this method being called.
        """
        self.vfcHost = None
        gsw_devices = gsw_conf.get_devices()
        self.switches = {}

        self.haswellNodeRange=(201,299)

        self.stitching_shadow_network_name = ''
        self.patchpanel_port_map = {}
        try:
            LOG.info("stitching_shadow_network: " + str(CONF.ngs_coordination.stitching_shadow_network))
            self.stitching_shadow_network_name = CONF.ngs_coordination.stitching_shadow_network

            LOG.info("patchpanel_switch: " + str(CONF.ngs_coordination.patchpanel_switch))
            self.patchpanel_switch_name = CONF.ngs_coordination.patchpanel_switch

            LOG.info("port_map: " + str(CONF.ngs_coordination.patchpanel_port_map))
            self.patchpanel_port_map = {}
            for port_str in CONF.ngs_coordination.port_map.split(','):
                port_name, port_id = port_str.split(":")
                self.patchpanel_port_map[port_name] = port_id
        except:
            LOG.info("stitching_shadow_network undefined")

        for switch_info, device_cfg in gsw_devices.items():
            switch = devices.device_manager(device_cfg)
            if hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                device_cfg['name']=switch_info
            self.switches[switch_info] = switch
            if 'VFCHost' in device_cfg and device_cfg['VFCHost'] == 'True':
                self.vfcHost = switch
            if 'sharedNonByocVFC' in device_cfg:
                self.sharedNonByocVFC = device_cfg['sharedNonByocVFC']
            if 'sharedNonByocVLAN' in device_cfg:
                self.sharedNonByocVLAN = device_cfg['sharedNonByocVLAN']
            if 'sharedNonByocProvider' in device_cfg:
                self.sharedNonByocProvider = device_cfg['sharedNonByocProvider']
            LOG.info('Devices - switch %s ', str(switch) )

        LOG.info('Devices - self.vfcHost %s ', str(self.vfcHost) )
        LOG.info('Devices %s have been loaded - keys   ', self.switches.keys())
        LOG.info('Devices %s have been loaded - values ', self.switches.values())
        if not self.switches:
            LOG.error('No devices have been loaded')
        self.warned_del_network = False

    def create_network_precommit(self, context):
        """Allocate resources for a new network.

        :param context: NetworkContext instance describing the new
        network.

        Create a new network, allocating resources as necessary in the
        database. Called inside transaction context on session. Call
        cannot block.  Raising an exception will result in a rollback
        of the current transaction.
        """
        pass

    def create_network_postcommit(self, context):
        """Create a network.

        :param context: NetworkContext instance describing the new
        network.

        Called after the transaction commits. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance. Raising an exception will
        cause the deletion of the resource.
        """

        network = context.current
        network_id = network['id']
        project_id = network['project_id'].strip()
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']
        physnet = network['provider:physical_network']

        of_controller = self.__get_of_controller(network)
        vfc_name = self.__get_vfc_name(network, project_id)

        LOG.debug("network: " + str(network) + ", network_id: " + str(network_id))

        if provider_type == 'vlan' and segmentation_id:
            # Create vlan on all switches from this driver
            for switch_name, switch in self._get_devices_by_physnet(physnet):
                try:
                    is_byoc_network = False
                    if hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                        if of_controller or vfc_name:
                            is_byoc_network = True
                        if is_byoc_network:
                            if vfc_name:
                                named_vfc_bridge = switch.find_named_vfc(vfc_name)
                                if named_vfc_bridge:
                                    LOG.debug("corsa-namedvfc - VFC exists - add_network_to_existing_vfc = " + str(named_vfc_bridge) )
                                    switch.add_network_to_existing_vfc(segmentation_id, network_id, named_vfc_bridge, vfc_name, of_controller)
                                else:
                                    LOG.debug("corsa-namedvfc - VFC does not exist - add_network = " + str(named_vfc_bridge) )
                                    switch.add_network(segmentation_id, network_id, project_id, of_controller, vfc_name)
                            else:
                                LOG.debug("corsa-unnamedvfc - custom ofcontroller - add_network " )
                                switch.add_network(segmentation_id, network_id, project_id, of_controller)
                        else:
                            if physnet == self.sharedNonByocProvider:
                                LOG.debug("corsa-unnamedvfc - sharedBYOC - add_network " )
                                switch.add_network_to_sharedNonByoc_vfc(segmentation_id, network_id)
                            else:
                                LOG.debug("corsa-unnamedvfc - BYOC - add_network " )
                                switch.add_network(segmentation_id, network_id, project_id)
                    else:
                        LOG.debug("dell-unnamedvfc - noofcontroller - add_network " )
                        switch.add_network(segmentation_id, network_id)

                except Exception as e:
                    LOG.error("Failed to create network %(net_id)s "
                              "on device: %(switch)s, reason: %(exc)s",
                              {'net_id': network_id,
                               'switch': switch_name,
                               'exc': e})
                else:
                    LOG.info('Network %(net_id)s has been added on device '
                             '%(device)s', {'net_id': network['id'],
                                            'device': switch_name})

    def __get_of_controller(self, network):
        if 'description' in network.keys():
            description = network['description'].strip()
            LOG.debug("Description = " + description )

            if description.startswith('OFController='):
                VFCparameters = description.split(',')
                key, controller = VFCparameters[0].split('=')
                cont_ip, cont_port = controller.strip().split(':')

                # Validate controller IP address and port
                try:
                    socket.inet_aton(cont_ip)
                except:
                    raise Exception("The provided controller IP address is invalid: %s", str(cont_ip))
                try:
                    cont_port = int(cont_port)
                    if cont_port < 0 or cont_port > 65535:
                        raise ValueError
                except:
                    raise Exception("The provided controller port is invalid: %s", str(cont_port))

                return cont_ip, cont_port

        return None

    def __get_vfc_name(self, network, project_id=None):
        if 'description' in network.keys():
            description = network['description'].strip()

            if description.startswith('OFController='):
                VFCparameters = description.split(',')

                if ( len(VFCparameters) > 1 ) and (VFCparameters[1].startswith('VSwitchName=')):
                    key, v_switch_name = VFCparameters[1].split('=')

                    if project_id:
                        vfc_name = project_id + "-" + v_switch_name
                    else:
                        vfc_name = "NONE-" + v_switch_name
                    LOG.debug("vfc_name: " + vfc_name )
                    # FIXME: Validate VFC name
                    try:
                        #if not bool(re.match('^[a-zA-Z0-9]+$', vfc_name)) and (len(vfc_name) < 25):
                        if (not v_switch_name.isalnum()) or len(v_switch_name) > 25:
                            raise ValueError
                    except:
                        raise Exception("Invalid VSwitch Name: %s", vfc_name)
                    return vfc_name

            elif description.startswith('VSwitchName='):
                key, v_switch_name = description.split('=')

                if project_id:
                    vfc_name = project_id + "-" + v_switch_name
                else:
                    vfc_name = "NONE-" + v_switch_name
                LOG.debug("vfc_name: " + vfc_name )
                # FIXME: Validate VFC name
                try:
                    if (not v_switch_name.isalnum()) or len(v_switch_name) > 25:
                        raise ValueError
                except:
                        raise Exception("Invalid VSwitch Name: %s", vfc_name)
                return vfc_name

        return None


    def update_network_precommit(self, context):
        """Update resources of a network.

        :param context: NetworkContext instance describing the new
        state of the network, as well as the original state prior
        to the update_network call.

        Update values of a network, updating the associated resources
        in the database. Called inside transaction context on session.
        Raising an exception will result in rollback of the
        transaction.

        update_network_precommit is called for all changes to the
        network state. It is up to the mechanism driver to ignore
        state or state changes that it does not know or care about.
        """
        pass

    def update_network_postcommit(self, context):
        """Update a network.

        :param context: NetworkContext instance describing the new
        state of the network, as well as the original state prior
        to the update_network call.

        Called after the transaction commits. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance. Raising an exception will
        cause the deletion of the resource.

        update_network_postcommit is called for all changes to the
        network state.  It is up to the mechanism driver to ignore
        state or state changes that it does not know or care about.
        """
        pass

    def delete_network_precommit(self, context):
        """Delete resources for a network.

        :param context: NetworkContext instance describing the current
        state of the network, prior to the call to delete it.

        Delete network resources previously allocated by this
        mechanism driver for a network. Called inside transaction
        context on session. Runtime errors are not expected, but
        raising an exception will result in rollback of the
        transaction.
        """
        pass

    def delete_network_postcommit(self, context):
        """Delete a network.

        :param context: NetworkContext instance describing the current
        state of the network, prior to the call to delete it.

        Called after the transaction commits. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance. Runtime errors are not
        expected, and will not prevent the resource from being
        deleted.
        """
        network = context.current
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']
        physnet = network['provider:physical_network']
        project_id = network['project_id'].strip()

        if provider_type == 'vlan' and segmentation_id:
            # Delete vlan on all switches from this driver
            for switch_name, switch in self._get_devices_by_physnet(physnet):
                try:
                    # NOTE(mgoddard): The del_network method was modified to
                    # accept the network ID. The switch object may still be
                    # implementing the old interface, so retry on a TypeError.
                    try:
                        switch.del_network(segmentation_id, network['id'])
                    except TypeError:
                        if not self.warned_del_network:
                            msg = (
                                'The del_network device method should accept '
                                'the network ID. Falling back to just the '
                                'segmentation ID for %(device)s. This '
                                'transitional support will be removed in the '
                                'Rocky release')
                            LOG.warn(msg, {'device': switch_name})
                            self.warned_del_network = True

                        # TODO(diurnalist): Either make use of network_id for
                        # this or pass the entire network
                        if hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                            switch.del_network(segmentation_id, project_id)
                        else:
                            switch.del_network(segmentation_id)
                except Exception as e:
                    LOG.error("Failed to delete network %(net_id)s "
                              "on device: %(switch)s, reason: %(exc)s",
                              {'net_id': network['id'],
                               'switch': switch_name,
                               'exc': e})
                else:
                    LOG.info('Network %(net_id)s has been deleted on device '
                             '%(device)s', {'net_id': network['id'],
                                            'device': switch_name})

    def create_subnet_precommit(self, context):
        """Allocate resources for a new subnet.

        :param context: SubnetContext instance describing the new
        subnet.
        rt = context.current
        device_id = port['device_id']
        device_owner = port['device_owner']
        Create a new subnet, allocating resources as necessary in the
        database. Called inside transaction context on session. Call
        cannot block.  Raising an exception will result in a rollback
        of the current transaction.
        """
        pass

    def create_subnet_postcommit(self, context):
        """Create a subnet.

        :param context: SubnetContext instance describing the new
        subnet.

        Called after the transaction commits. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance. Raising an exception will
        cause the deletion of the resource.
        """
        pass

    def update_subnet_precommit(self, context):
        """Update resources of a subnet.

        :param context: SubnetContext instance describing the new
        state of the subnet, as well as the original state prior
        to the update_subnet call.

        Update values of a subnet, updating the associated resources
        in the database. Called inside transaction context on session.
        Raising an exception will result in rollback of the
        transaction.

        update_subnet_precommit is called for all changes to the
        subnet state. It is up to the mechanism driver to ignore
        state or state changes that it does not know or care about.
        """
        pass

    def update_subnet_postcommit(self, context):
        """Update a subnet.

        :param context: SubnetContext instance describing the new
        state of the subnet, as well as the original state prior
        to the update_subnet call.

        Called after the transaction commits. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance. Raising an exception will
        cause the deletion of the resource.

        update_subnet_postcommit is called for all changes to the
        subnet state.  It is up to the mechanism driver to ignore
        state or state changes that it does not know or care about.
        """
        pass

    def delete_subnet_precommit(self, context):
        """Delete resources for a subnet.

        :param context: SubnetContext instance describing the current
        state of the subnet, prior to the call to delete it.

        Delete subnet resources previously allocated by this
        mechanism driver for a subnet. Called inside transaction
        context on session. Runtime errors are not expected, but
        raising an exception will result in rollback of the
        transaction.
        """
        pass

    def delete_subnet_postcommit(self, context):
        """Delete a subnet.

        :param context: SubnetContext instance describing the current
        state of the subnet, prior to the call to delete it.

        Called after the transaction commits. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance. Runtime errors are not
        expected, and will not prevent the resource from being
        deleted.
        """
        pass

    def create_port_precommit(self, context):
        """Allocate resources for a new port.

        :param context: PortContext instance describing the port.

        Create a new port, allocating resources as necessary in the
        database. Called inside transaction context on session. Call
        cannot block.  Raising an exception will result in a rollback
        of the current transaction.
        """
        pass

    def create_port_postcommit(self, context):
        """Create a port.

        :param context: PortContext instance describing the port.

        Called after the transaction compt6letes. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance.  Raising an exception will
        result in the deletion of the resource.
        """
        import json
        LOG.debug("" + json.dumps(str(context.__dict__), indent=2))
        LOG.debug("" + str(context.current))

        from neutron.objects.ports import Port
        from neutron.objects import ports as port_obj
        from neutron.objects import network as network_obj
        from neutron_lib import context as lib_context
        from neutron.objects import tag as tag_obj
        from neutron_lib.plugins import directory

        admin_context = lib_context.get_admin_context()
        LOG.debug("XXXXXX admin_context, " + str(admin_context))

        LOG.debug("XXXXXX Networks")
        for net in network_obj.Network.get_objects(admin_context):
            LOG.debug("XXXXXX Net: " + str(net))
            if str(net['name']) == self.stitching_shadow_network_name:
                LOG.debug("XXXXXX FOUND SHADOW STITCH NETWORK: " + str(net['name']) + ", " + str(net))
                stitching_shadow_network = net
                stitching_shadow_network_id = net['id']

        #LOG.debug("XXXXXX Ports, ")
        #for port in port_obj.Port.get_objects(admin_context):
        #    LOG.debug("XXXXXX Port: " + str(port))
        #    if port['network_id'] == stitching_shadow_network_id:
        #        shadow_port = port
        #        LOG.debug("XXXXXX FOUND SHADOW STITCH Port: " + str(port))

        port = context.current
        port_id = port['id']

        LOG.debug("port: " + str(port))
        # network_id = port['network_id']

        # LOG.debug("create_port_postcommit: port_id: " + str(port_id) + ", network_id: " + str(network_id))

        # admin_context = lib_context.get_admin_context()
        # network = network_obj.Network.get_objects(admin_context,id=network_id)[0]
        network = context.network.current

        LOG.debug("create_port_postcommit: network: " + str(network))

        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']
        physnet = network['provider:physical_network']
        project_id = network['project_id'].strip()
        LOG.debug('project_id: ' + str(project_id))


        port_type = None
        if 'type' in port['binding:profile']:
            port_type = port['binding:profile']['type']

        if network['name'] == 'stitching_shadow_network':
            LOG.info('adding shadow port. no physical config required')
            LOG.debug('port:  ' + str(port))
        elif port_type == 'stitchport':
            LOG.debug('Adding stitch port: port_type: ' + str(port_type))
            LOG.debug('patchpanel_port_map:  ' + str(self.patchpanel_port_map))

            # Check if stitchport is authorized by blazar/shadow network
            #TODO

            if 'reservation_id' in port['binding:profile']:
                reservation_id = port['binding:profile']['reservation_id']

            LOG.debug("XXXXXX Searching for shadow port, ")
            shadow_port = None
            for shadow_port_candidate in port_obj.Port.get_objects(admin_context):
                try:
                    # Prints the nicely formatted dictionary
                    #pprint.pprint(shadow_port)
                    #pprint.pformat(dictionary)
                    #import json
                    #print(json.dumps(dictionary, indent=4, sort_keys=True))

                    #LOG.debug("Candidate shadow_port (pretty2): " + json.dumps(shadow_port_candidate, default=str, indent=4))
                    LOG.debug("Candidate shadow_port (pretty2): " + str(shadow_port_candidate))

                    if shadow_port_candidate['name'] == 'pruth1_shadowport':
                        LOG.debug("XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")

                    binding = None
                    for binding_candidate in shadow_port_candidate['bindings']:
                        LOG.debug("shadow_port_candidate['bindings'] type: " + str(type(binding_candidate)))
                        LOG.debug("shadow_port_candidate['bindings'] binding: " + str(binding_candidate))
                        #if binding_candidate['project_id'] != None:
                        #    binding = binding_candidate
                        #    break

                    binding = shadow_port_candidate['bindings'][0]

                    #shadow_port['bindings'] binding: PortBinding(host='',port_id=b12d066a-469e-41fa-9ada-dc3cf9f1c468,profile={"type": "shadow", "project_id": "1234567890", "reservation_id": "abcdefg", "vlan": "1234", "stitchport": "fabric"},status='ACTIVE',vif_details=None,vif_type='unbound',vnic_type='normal')

                    #LOG.debug("Candidate shadow_port: " + str(shadow_port))
                    #if not 'bindings' in shadow_port['bindings']:
                    #if hasattr(shadow_port_candidate,'bindings') and shadow_port_candidate['bindings'] == None:
                    #if shadow_port_candidate['bindings'] == None and 'project_id' in shadow_port_candidate['bindings'].keys() and  'reservation_id' in shadow_port_candidate['bindings'].keys() :
                    #    LOG.debug("port does not have bindings or stitchport info, skipping")
                    #    continue
                    LOG.debug("\nproject_id " + str(project_id))
                    LOG.debug("\nreservation_id " + str(reservation_id))
                    LOG.debug("\nshadow_port_candidate['bindings']['profile']['project_id'] " + str(shadow_port_candidate['bindings'][0]['profile']['project_id']))
                    LOG.debug("\nshadow_port_candidate['bindings']['profile']['reservation_id'] " + str(shadow_port_candidate['bindings'][0]['profile']['reservation_id']))
                    LOG.debug("\nshadow_port_candidate['network_id'] " + str(shadow_port_candidate['network_id']))
                    LOG.debug("\nstitching_shadow_network['id'] " + str(stitching_shadow_network['id']))



                    if shadow_port_candidate['network_id'] == stitching_shadow_network['id'] and \
                            shadow_port_candidate['bindings'][0]['profile']['project_id'] == project_id and \
                            shadow_port_candidate['bindings'][0]['profile']['reservation_id'] == reservation_id:
                        shadow_port = shadow_port_candidate
                        LOG.debug("XXXXXX FOUND SHADOW STITCH Port: " + str(port))
                        break
                except Exception as e:
                    LOG.debug("Excpetion in testing shadow_port_candidate: " + str(e)  + ", shadow_port_candidate: " + str(shadow_port_candidate))
                    continue

            if shadow_port == None:
                LOG.debug("XXXXXX SHADOW STITCH NOT FOUND!")
                raise Exception("SHADOW STITCH NOT FOUND!")

            #get shadow vlan and stitchport from shadow port
            stichport_name = shadow_port['bindings']['stitchport']
            stichport_vlan = shadow_port['bindings']['vlan']

            # Add patch
            try:
                for switch_name, switch in self._get_devices_by_physnet(physnet):
                    LOG.debug("Searching for patchpanel switch (" + self.patchpanel_switch_name + ". candidate: " + str(switch_name))
                    if switch_name == self.patchpanel_switch_name:
                        self.patchpanel_switch = switch
                        break

                port1_name = self.patchpanel_port_map[stichport_name]
                port1_vlan = stichport_vlan
                port2_name = self.patchpanel_port_map[physnet]
                port2_vlan = segmentation_id
                LOG.debug('Adding patch: ' + str(self.patchpanel_switch) +
                          ', port1_name: ' + str(port1_name) +
                          ', port1_vlan: ' + str(port1_vlan) +
                          ', port2_name: ' + str(port2_name) +
                          ', port2_vlan: ' + str(port2_vlan)
                          )
                self.patchpanel_switch.add_patch(patch_id='2100',
                                 port1_name=port1_name,
                                 port1_vlan=port1_vlan,
                                 port2_name=port2_name,
                                 port2_vlan=port2_vlan)
            except Exception as e:
                LOG.error(e)

        elif provider_type == 'vlan' and segmentation_id:
            # if the port is an internal port for connecting a server
            for switch_name, switch in self._get_devices_by_physnet(physnet):
                # Skip configuring the patchpanel for regular networks
                if hasattr(self, 'patchpanel_switch_name') and switch_name == self.patchpanel_switch_name:
                    LOG.debug("Skipping patchpaned switch config for vlan network")
                    continue

                try:
                    if switch_name in self.provisionable_switches and physnet == \
                            self.provisionable_switches[switch_name]['device_cfg']['chi_provider_net_name']:
                        if segmentation_id in self.provisionable_switches[switch_name]['switch_map']:
                            LOG.debug("corsa - custom controller - add_port ")
                            switch.add_port(port_id, segmentation_id)

                except Exception as e:
                    LOG.error("Failed to delete network %(net_id)s "
                              "on device: %(switch)s, reason: %(exc)s",
                              {'net_id': network['id'],
                               'switch': switch_name,
                               'exc': e})

    def update_port_precommit(self, context):
        """Update resources of a port.

        :param context: PortContext instance describing the new
        state of the port, as well as the original state prior
        to the update_port call.

        Called inside transaction context on session to complete a
        port update as defined by this mechanism driver. Raising an
        exception will result in rollback of the transaction.

        update_port_precommit is called for all changes to the port
        state. It is up to the mechanism driver to ignore state or
        state changes that it does not know or care about.
        """
        pass

    def update_port_postcommit(self, context):
        """Update a port.

        :param context: PortContext instance describing the new
        state of the port, as well as the original state prior
        to the update_port call.

        Called after the transaction completes. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance.  Raising an exception will
        result in the deletion of the resource.

        update_port_postcommit is called for all changes to the port
        state. It is up to the mechanism driver to ignore state or
        state changes that it does not know or care about.
        """
        port = context.current
        if self._is_port_bound(port):
            binding_profile = port['binding:profile']
            local_link_information = binding_profile.get(
                'local_link_information')
            if not local_link_information:
                return
            switch_info = local_link_information[0].get('switch_info')
            switch_id = local_link_information[0].get('switch_id')
            switch = device_utils.get_switch_device(
                self.switches, switch_info=switch_info,
                ngs_mac_address=switch_id)
            if not switch:
                return
            provisioning_blocks.provisioning_complete(
                context._plugin_context, port['id'], resources.PORT,
                GENERIC_SWITCH_ENTITY)
        elif self._is_port_bound(context.original):
            # The port has been unbound. This will cause the local link
            # information to be lost, so remove the port from the network on
            # the switch now while we have the required information.
            self._unplug_port_from_network(context.original,
                                           context.network.current)

    def delete_port_precommit(self, context):
        """Delete resources of a port.

        :param context: PortContext instance describing the current
        state of the port, prior to the call to delete it.

        Called inside transaction context on session. Runtime errors
        are not expected, but raising an exception will result in
        rollback of the transaction.
        """
        pass

    def delete_port_postcommit(self, context):
        """Delete a port.

        :param context: PortContext instance describing the current
        state of the port, prior to the call to delete it.

        Called after the transaction completes. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance.  Runtime errors are not
        expected, and will not prevent the resource from being
        deleted.
        """

        port = context.current
        if self._is_port_bound(port):
            self._unplug_port_from_network(port, context.network.current)

    def bind_port(self, context):
        """Attempt to bind a port.

        :param context: PortContext instance describing the port

        This method is called outside any transaction to attempt to
        establish a port binding using this mechanism driver. Bindings
        may be created at each of multiple levels of a hierarchical
        network, and are established from the top level downward. At
        each level, the mechanism driver determines whether it can
        bind to any of the network segments in the
        context.segments_to_bind property, based on the value of the
        context.host property, any relevant port or network
        attributes, and its own knowledge of the network topology. At
        the top level, context.segments_to_bind contains the static
        segments of the port's network. At each lower level of
        binding, it contains static or dynamic segments supplied by
        the driver that bound at the level above. If the driver is
        able to complete the binding of the port to any segment in
        context.segments_to_bind, it must call context.set_binding
        with the binding details. If it can partially bind the port,
        it must call context.continue_binding with the network
        segments to be used to bind at the next lower level.

        If the binding results are committed after bind_port returns,
        they will be seen by all mechanism drivers as
        update_port_precommit and update_port_postcommit calls. But if
        some other thread or process concurrently binds or updates the
        port, these binding results will not be committed, and
        update_port_precommit and update_port_postcommit will not be
        called on the mechanism drivers with these results. Because
        binding results can be discarded rather than committed,
        drivers should avoid making persistent state changes in
        bind_port, or else must ensure that such state changes are
        eventually cleaned up.

        Implementing this method explicitly declares the mechanism
        driver as having the intention to bind ports. This is inspected
        by the QoS service to identify the available QoS rules you
        can use with ports.
        """

        port = context.current
        binding_profile = port['binding:profile']
        local_link_information = binding_profile.get('local_link_information')
        LOG.info("Bindport, port: " + str(port) + ", binding_profile: " + str(binding_profile))

        if self._is_port_supported(port) and local_link_information:
            switch_info = local_link_information[0].get('switch_info')
            switch_id = local_link_information[0].get('switch_id')
            sdn_node_id = str(switch_id)[-3:]
            haswell_sdn = False

            switch = device_utils.get_switch_device(
                self.switches, switch_info=switch_info,
                ngs_mac_address=switch_id)

            LOG.debug("Bindport - switch %s : " + str(switch))
            if not switch:
                return
            network = context.network.current
            physnet = network['provider:physical_network']
            switch_physnets = switch._get_physical_networks()

            ### Determine if the network is BYOC 
            network_id = network['id']
            project_id = network['project_id'].strip()
            of_controller = self.__get_of_controller(network)
            vfc_name = self.__get_vfc_name(network, project_id)
            if of_controller or vfc_name:
                is_byoc_network = True 
            else:
                is_byoc_network = False
            LOG.debug("Bindport: is_byoc_network : " + str(is_byoc_network) )

            if switch_physnets and physnet not in switch_physnets:
                LOG.error("Cannot bind port %(port)s as device %(device)s is "
                          "not on physical network %(physnet)",
                          {'port_id': port['id'], 'device': switch_info,
                           'physnet': physnet})
                return
            port_id = local_link_information[0].get('port_id')
            segments = context.segments_to_bind
            # If segmentation ID is None, set vlan 1
            segmentation_id = segments[0].get('segmentation_id') or '1'
            provisioning_blocks.add_provisioning_component(
                context._plugin_context, port['id'], resources.PORT,
                GENERIC_SWITCH_ENTITY)
            LOG.debug("Putting port {port} on {switch_info} to vlan: "
                      "{segmentation_id}".format(
                          port=port_id,
                          switch_info=switch_info,
                          segmentation_id=segmentation_id))

            LOG.debug("Bindport - haswellNodeRange %s : " + str(self.haswellNodeRange[0]))
            LOG.debug("Bindport - haswellNodeRange %s : " + str(self.haswellNodeRange[1]))
            ### Determine if the node is a haswell node 
            if is_byoc_network and int(sdn_node_id) in range(int(self.haswellNodeRange[0]),int(self.haswellNodeRange[1])):
                haswell_sdn = True
            
            LOG.debug("Bindport - sdn_node_id : " + str(sdn_node_id))
            LOG.debug("Bindport - haswell_sdn : " + str(haswell_sdn))
            LOG.debug("Bindport - segmentation_id : " + str(segmentation_id))

            # Move port to network

            if hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                switch.plug_port_to_network(port_id, segmentation_id, sdn_node_id, vfc_host=self.vfcHost)
            else:
                if haswell_sdn:
                    LOG.debug("Bindport - haswell_sdn : " + str(haswell_sdn))
                    LOG.debug("Bindport - selfvfcHost %s : " + str(self.vfcHost))
                    switch.plug_port_to_network(port_id, sdn_node_id)
                    self.vfcHost.plug_port_to_network_haswellsdn(port_id, segmentation_id, sdn_node_id, vfc_host=self.vfcHost)
                else:
                    switch.plug_port_to_network(port_id, segmentation_id)


            LOG.info("Successfully bound port %(port_id)s in segment "
                     "%(segment_id)s on device %(device)s",
                     {'port_id': port['id'], 'device': switch_info,
                      'segment_id': segmentation_id})
            context.set_binding(segments[0][api.ID],
                                portbindings.VIF_TYPE_OTHER, {})

    @staticmethod
    def _is_port_supported(port):
        """Return whether a port is supported by this driver.

        Ports supported by this driver have a VNIC type of 'baremetal'.

        :param port: The port to check
        :returns: Whether the port is supported by the NGS driver
        """
        vnic_type = port[portbindings.VNIC_TYPE]
        return vnic_type == portbindings.VNIC_BAREMETAL

    @staticmethod
    def _is_port_bound(port):
        """Return whether a port is bound by this driver.

        Ports bound by this driver have their VIF type set to 'other'.

        :param port: The port to check
        :returns: Whether the port is bound by the NGS driver
        """
        if not GenericSwitchDriver._is_port_supported(port):
            return False

        vif_type = port[portbindings.VIF_TYPE]
        return vif_type == portbindings.VIF_TYPE_OTHER

    def _unplug_port_from_network(self, port, network):
        """Unplug a port from a network.

        If the configuration required to unplug the port is not present
        (e.g. local link information), the port will not be unplugged and no
        exception will be raised.

        :param port: The port to unplug
        :param network: The network from which to unplug the port
        """
        binding_profile = port['binding:profile']
        local_link_information = binding_profile.get('local_link_information')
        if not local_link_information:
            return
        switch_info = local_link_information[0].get('switch_info')
        switch_id = local_link_information[0].get('switch_id')
        sdn_node_id = str(switch_id)[-3:]
        haswell_sdn = False

        switch = device_utils.get_switch_device(
            self.switches, switch_info=switch_info,
            ngs_mac_address=switch_id)

        if not switch:
            return
        port_id = local_link_information[0].get('port_id')
        # If segmentation ID is None, set vlan 1
        segmentation_id = network.get('provider:segmentation_id') or '1'
        LOG.debug("Unplugging port {port} on {switch_info} from vlan: "
                  "{segmentation_id}".format(
                      port=port_id,
                      switch_info=switch_info,
                      segmentation_id=segmentation_id))

        ### Determine if the network is BYOC 
        network_id = network['id']
        project_id = network['project_id'].strip()
        of_controller = self.__get_of_controller(network)
        vfc_name = self.__get_vfc_name(network, project_id)
        if of_controller or vfc_name:
            is_byoc_network = True
        else:
            is_byoc_network = False
        LOG.debug("_unplug_port_from_network: is_byoc_network : " + str(is_byoc_network) )

        LOG.debug("_unplug_port_from_network - haswellNodeRange : " + str(self.haswellNodeRange[0]))
        LOG.debug("_unplug_port_from_network - haswellNodeRange : " + str(self.haswellNodeRange[1]))
        ### Determine if the node is a haswell node 
        if is_byoc_network and int(sdn_node_id) in range(int(self.haswellNodeRange[0]),int(self.haswellNodeRange[1])):
            haswell_sdn = True

        LOG.debug("_unplug_port_from_network - sdn_node_id : " + str(sdn_node_id))
        LOG.debug("_unplug_port_from_network - haswell_sdn : " + str(haswell_sdn))
        LOG.debug("_unplug_port_from_network - segmentation_id : " + str(segmentation_id))


        try:
            if hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                switch.delete_port(port_id, segmentation_id, sdn_node_id, vfc_host=self.vfcHost)
            else:
                if haswell_sdn:
                    LOG.debug("Bindport - haswell_sdn : " + str(haswell_sdn))
                    LOG.debug("Bindport - selfvfcHost %s : " + str(self.vfcHost))
                    switch.delete_port(port_id, sdn_node_id)
                    self.vfcHost.delete_port(port_id, segmentation_id, sdn_node_id, vfc_host=self.vfcHost)
                else:
                    switch.delete_port(port_id, segmentation_id)

        except Exception as e:
            LOG.error("Failed to unplug port %(port_id)s "
                      "on device: %(switch)s from network %(net_id)s "
                      "reason: %(exc)s",
                      {'port_id': port['id'], 'net_id': network['id'],
                       'switch': switch_info, 'exc': e})
            raise e
        LOG.info('Port %(port_id)s has been unplugged from network '
                 '%(net_id)s on device %(device)s',
                 {'port_id': port['id'], 'net_id': network['id'],
                  'device': switch_info})

    def _get_devices_by_physnet(self, physnet):
        """Generator yielding switches on a particular physical network.

        :param physnet: Physical network to filter by.
        :returns: Yields 2-tuples containing the name of the switch and the
            switch device object.
        """
        for switch_name, switch in self.switches.items():
            physnets = switch._get_physical_networks()
            # NOTE(mgoddard): If the switch has no physical networks then
            # follow the old behaviour of mapping all networks to it.
            if not physnets or physnet in physnets:
                yield switch_name, switch
