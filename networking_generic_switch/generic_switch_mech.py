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
import socket
import re



from networking_generic_switch import config as gsw_conf
from networking_generic_switch import devices
from networking_generic_switch.devices import utils as device_utils

LOG = logging.getLogger(__name__)

GENERIC_SWITCH_ENTITY = 'GENERICSWITCH'


class GenericSwitchDriver(api.MechanismDriver):

    def initialize(self):
        """Perform driver initialization.

        Called after all drivers have been loaded and the database has
        been initialized. No abstract methods defined below will be
        called prior to this method being called.
        """
        LOG.info("Initializing GenericSwitchDriver")
        gsw_devices = gsw_conf.get_devices()
        self.switches = {}
        self.patchpanels = {}
        self.leafs = {}
        self.provisionables = {}

        for switch_info, device_cfg in gsw_devices.items():
            switch = devices.device_manager(device_cfg)
            self.switches[switch_info] = switch

            if not 'chi_switch_role' in device_cfg or device_cfg['chi_switch_role'] == 'leaf':
                if not 'chi_switch_role' in device_cfg:
                    LOG.warning("Adding switch without chi_switch_role. Assuming chi_switch_role = leaf")

                LOG.info("Adding leaf switch")
                self.leafs[switch_info] = switch

            elif 'chi_switch_role' in device_cfg and device_cfg['chi_switch_role'] == 'patchpanel':
                LOG.info("Adding patchpanel switch")
                self.patchpanels[switch_info]= switch
            elif 'chi_switch_role' in device_cfg and device_cfg['chi_switch_role'] == 'provisionable':
                LOG.info("Adding provisionable switch")
                self.provisionables[switch_info]= switch
            else:
                LOG.error("Attempted to Add switch with unkown chi_switch_role. Skipping. %s", str(switch))

        if not self.switches:
            LOG.error('No devices have been loaded')
        self.warned_del_network = False


        LOG.debug("switches: " + str(self.switches))
        LOG.debug("self.patchpanels: " + str(self.patchpanels))
        LOG.debug("self.leafs: " + str(self.leafs))
        LOG.debug("self.provisionables: " + str(self.provisionables))

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

	import json
        LOG.debug("create_network_postcommit: " + json.dumps(context.current, indent=2))
        

        network = context.current
        network_id = network['id']
        project_id = network['project_id'].strip()
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']
        physnet = network['provider:physical_network']

        if provider_type == 'vlan' and segmentation_id:
            
            extraArgs=self.__get_extra_network_config(network)
            LOG.debug("extraArgs = " + str(extraArgs))

            #of_controller = self.__get_of_controller(network)
            # Create vlan on all switches from this driver
            for switch_name, switch in self._get_devices_by_physnet(physnet):
                try:
                    if switch_name in self.patchpanels:
                        continue

                    if extraArgs['switch-type'] == 'corsa':
                        #if isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):  
                        if switch_name in self.provisionables:
                            #and hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                            LOG.debug("corsa-unnamedvfc - custom ofcontroller - add_network " )
                            switch.add_network(segmentation_id, network_id, project_id, [extraArgs['ofcontroller_ip'],extraArgs['ofcontroller_port']])
                    else:
                        LOG.debug("regular isolated vlan network - add_network " )
                        switch.add_network(segmentation_id, network_id)

                except Exception as e:
                    LOG.error("Failed to create network %(net_id)s "
                              "on device: %(switch)s, reason: %(exc)s",
                              {'net_id': network_id,
                               'switch': switch_name,
                               'exc': e})
                #LOG.info('Network %(net_id)s has been added on device '
                #         '%(device)s', {'net_id': network['id'],
                #                        'device': switch_name})

    def __get_extra_network_config(self, network):
        """Gets config arguments from description field for chi networks

        switch-type=corsa etc.
        OFController=${OF_CONTROLLER_IP}:${OF_CONTROLLER_PORT}
        VSwitchName= depricated
        """
        rtnArgs={}

        try:

            if 'description' in network.keys():
                description = network['description'].strip()
                LOG.debug("__get_extra_network_config - Description = " + str(description) )

                rawArgs = description.split(',')
            
            
                for rawArg in rawArgs:
                    key, value = rawArg.split('=')
                
                    LOG.debug("__get_extra_network_config. key = " + str(key) +", value = " + str(value))
                    if key.startswith('OFController'):
                        LOG.debug("__get_extra_network_config. Adding ofcontroller args: value: " + str(value))
                        ofcontroller_ip, ofcontroller_port = value.strip().split(':')
                        LOG.debug("__get_extra_network_config. ofcontroller_ip = " + str(ofcontroller_ip) + ", ofcontroller_port = " + str(ofcontroller_port))
                        try:
                            socket.inet_aton(ofcontroller_ip)
                        except:
                            LOG.error("The provided controller IP address is invalid: %s", str(ofcontroller_ip))
                            raise Exception("The provided controller IP address is invalid: %s", str(ofcontroller_ip))
                
                        try:
                            ofcontroller_port = int(ofcontroller_port)
                            if ofcontroller_port < 0 or ofcontroller_port > 65535:
                                LOG.error("The provided controller port is invalid: %s", str(ofcontroller_port))
                                raise ValueError
                        except:
                            LOG.error("The provided controller port is invalid: %s", str(ofcontroller_port))
                            raise Exception("The provided controller port is invalid: %s", str(ofcontroller_port))

                        rtnArgs['ofcontroller_ip']=ofcontroller_ip
                        rtnArgs['ofcontroller_port']=ofcontroller_port
                    else:
                        LOG.debug("__get_extra_network_config. Adding other arg")
                        key, value = rawArg.split('=')
                        rtnArgs[key]=value
                    
        except:
            LOG.debug("__get_extra_network_config. excpetion in processing description: ")
        

        return rtnArgs

        

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
        import json
        LOG.debug("update_network_postcommit: " + json.dumps(context.current, indent=2))

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
            
            extraArgs=self.__get_extra_network_config(network)
            LOG.debug("extraArgs = " + str(extraArgs))

            # Delete vlan on all switches from this driver
            for switch_name, switch in self._get_devices_by_physnet(physnet):

                if switch_name in self.patchpanels:
                    continue


                try:
                    if extraArgs['switch-type'] == 'corsa':
                        #if isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):                                                                                                       
                        if switch_name in self.provisionables:
                            #and hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):                                                             
                            LOG.debug("corsa - custom ofcontroller - add_network " )
                            #switch.del_network(segmentation_id, network_id, project_id, [extraArgs['ofcontroller_ip'],extraArgs['ofcontroller_port']])
                            switch.del_network(segmentation_id, project_id) 
                    else:
                        LOG.debug("regular isolated vlan network - del network " )
                        switch.del_network(segmentation_id)

                except Exception as e:
                    LOG.error("Failed to delete network %(net_id)s "
                              "on device: %(switch)s, reason: %(exc)s",
                              {'net_id': network['id'],
                               'switch': switch_name,
                               'exc': e})
   

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
        import json
        LOG.debug("create_port_precommit: " + json.dumps(context.current, indent=2))

        pass

    def create_port_postcommit(self, context):
        """Create a port.

        :param context: PortContext instance describing the port.

        Called after the transaction completes. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance.  Raising an exception will
        result in the deletion of the resource.
        """
        import json
        LOG.debug("create_port_postcommit: " + json.dumps(context.current, indent=2))


        pass

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
        import json
        LOG.debug("update_port_precommit: " + json.dumps(context.current, indent=2))


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

	import json
        LOG.debug("update_port_postcommit: " + json.dumps(context.current, indent=2))

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
        import json
        LOG.debug("delete_port_precommit: " + json.dumps(context.current, indent=2))


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
        import json
        LOG.debug("delete_port_postcommit: " + json.dumps(context.current, indent=2))

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
        import json
        LOG.debug("bind_port: " + json.dumps(context.current, indent=2))

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

            LOG.info("Bindport - switch %s : " + str(switch))
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
            LOG.info("Bindport: is_byoc_network : " + str(is_byoc_network) )

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

            LOG.info("Bindport - haswellNodeRange %s : " + str(self.haswellNodeRange[0]))
            LOG.info("Bindport - haswellNodeRange %s : " + str(self.haswellNodeRange[1]))
            ### Determine if the node is a haswell node 
            if is_byoc_network and int(sdn_node_id) in range(int(self.haswellNodeRange[0]),int(self.haswellNodeRange[1])):
                haswell_sdn = True
            
            LOG.info("Bindport - sdn_node_id : " + str(sdn_node_id))
            LOG.info("Bindport - haswell_sdn : " + str(haswell_sdn))
            LOG.info("Bindport - segmentation_id : " + str(segmentation_id))

            # Move port to network

            if hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                switch.plug_port_to_network(port_id, segmentation_id, sdn_node_id, vfc_host=self.vfcHost)
            else:
                if haswell_sdn:
                    LOG.info("Bindport - haswell_sdn : " + str(haswell_sdn))
                    LOG.info("Bindport - selfvfcHost %s : " + str(self.vfcHost))
                    switch.plug_port_to_network(port_id, sdn_node_id)
                    self.vfcHost.plug_port_to_network_haswellsdn(port_id, segmentation_id, sdn_node_id, vfc_host=self.vfcHost)
                else:
                    switch.plug_port_to_network(port_id, segmentation_id)


            LOG.info("Successfully bound port %(port_id)s in segment "
                     "%(segment_id)s on device %(device)s",
                     {'port_id': port['id'], 'device': switch_info,
                      'segment_id': segmentation_id})
            LOG.info("bind_port: 280")
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
        LOG.info("_unplug_port_from_network: is_byoc_network : " + str(is_byoc_network) )

        LOG.info("_unplug_port_from_network - haswellNodeRange : " + str(self.haswellNodeRange[0]))
        LOG.info("_unplug_port_from_network - haswellNodeRange : " + str(self.haswellNodeRange[1]))
        ### Determine if the node is a haswell node 
        if is_byoc_network and int(sdn_node_id) in range(int(self.haswellNodeRange[0]),int(self.haswellNodeRange[1])):
            haswell_sdn = True

        LOG.info("_unplug_port_from_network - sdn_node_id : " + str(sdn_node_id))
        LOG.info("_unplug_port_from_network - haswell_sdn : " + str(haswell_sdn))
        LOG.info("_unplug_port_from_network - segmentation_id : " + str(segmentation_id))


        try:
            if hasattr(devices,'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                switch.delete_port(port_id, segmentation_id, sdn_node_id, vfc_host=self.vfcHost)
            else:
                if haswell_sdn:
                    LOG.info("Bindport - haswell_sdn : " + str(haswell_sdn))
                    LOG.info("Bindport - selfvfcHost %s : " + str(self.vfcHost))
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
