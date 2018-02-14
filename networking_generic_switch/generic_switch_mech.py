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

from neutron.callbacks import resources
from neutron.db import provisioning_blocks
from neutron.plugins.ml2 import driver_api
from neutron_lib.api.definitions import portbindings
from oslo_log import log as logging

from networking_generic_switch import config as gsw_conf
from networking_generic_switch import devices
from networking_generic_switch.devices import utils as device_utils

LOG = logging.getLogger(__name__)

GENERIC_SWITCH_ENTITY = 'GENERICSWITCH'


class GenericSwitchDriver(driver_api.MechanismDriver):

    def initialize(self):
        """Perform driver initialization.

        Called after all drivers have been loaded and the database has
        been initialized. No abstract methods defined below will be
        called prior to this method being called.
        """

        gsw_devices = gsw_conf.get_devices()
        self.switches = {}
        for switch_info, device_cfg in gsw_devices.items():
            switch = devices.device_manager(device_cfg)
            self.switches[switch_info] = switch
        LOG.info('Devices %s have been loaded', self.switches.keys())
        if not self.switches:
            LOG.error('No devices have been loaded')

    def create_network_precommit(self, context):
        """Allocate resources for a new network.

        :param context: NetworkContext instance describing the new
        network.

        Create a new network, allocating resources as necessary in the
        database. Called inside transaction context on session. Call
        cannot block.  Raising an exception will result in a rollback
        of the current transaction.
        """
        LOG.info("PRUTH: create_network_precommit" + str(context))
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
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']

        LOG.info("PRUTH: create_network_postcommit: " + str(network))

        if provider_type == 'vlan' and segmentation_id:
            # Create vlan on all switches from this driver
            for switch_name, switch in self.switches.items():
                try:
                    switch.add_network(segmentation_id, network_id)
                except Exception as e:
                    LOG.error("Failed to create network %(net_id)s "
                              "on device: %(switch)s, reason: %(exc)s",
                              {'net_id': network_id,
                               'switch': switch_name,
                               'exc': e})
                LOG.info('Network %(net_id)s has been added on device '
                         '%(device)s', {'net_id': network['id'],
                                        'device': switch_name})

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
        LOG.info("PRUTH: update_network_precommit" + str(context))
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
        LOG.info("PRUTH: update_network_postcommit" + str(context))
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
        LOG.info("PRUTH: delete_network_precommit" + str(context))
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

        LOG.info("PRUTH: delete_network_postcommit: " + str(network))
        if provider_type == 'vlan' and segmentation_id:
            # Delete vlan on all switches from this driver
            for switch_name, switch in self.switches.items():
                try:
                    switch.del_network(segmentation_id)
                except Exception as e:
                    LOG.error("Failed to delete network %(net_id)s "
                              "on device: %(switch)s, reason: %(exc)s",
                              {'net_id': network['id'],
                               'switch': switch_name,
                               'exc': e})
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
        LOG.info("PRUTH: create_subnet_precommit" + str(context))
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
        LOG.info("PRUTH: create_subnet_postcommit" + str(context))
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
        LOG.info("PRUTH: update_subnet_precommit" + str(context))
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
        LOG.info("PRUTH: update_subnet_postcommit" + str(context))
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
        LOG.info("PRUTH: delete_subnet_precommit" + str(context))
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
        LOG.info("PRUTH: delete_subnet_postcommit" + str(context))
        pass

    def create_port_precommit(self, context):
        """Allocate resources for a new port.

        :param context: PortContext instance describing the port.

        Create a new port, allocating resources as necessary in the
        database. Called inside transaction context on session. Call
        cannot block.  Raising an exception will result in a rollback
        of the current transaction.
        """
        LOG.info("PRUTH: create_port_precommit" + str(context))
        pass

    def create_port_postcommit(self, context):
        """Create a port.

        :param context: PortContext instance describing the port.

        Called after the transaction completes. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance.  Raising an exception will
        result in the deletion of the resource.
        """
        LOG.info("PRUTH: create_port_postcommit: context: " + str(context))
        
        port = context.current

        LOG.info("PRUTH: create_port_postcommit: port: " + str(port))

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
        LOG.info("PRUTH: update_port_precommit" + str(context))
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
        LOG.info("PRUTH: update_port_postcommit: context: " + str(context))

        port = context.current

        LOG.info("PRUTH: update_port_postcommit: port: " + str(port))

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
        LOG.info("PRUTH: delete_port_precommit" + str(context))
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
        LOG.info("PRUTH: delete_port_postcommit" + str(context))

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
        LOG.info("PRUTH: bind_port: context: " + str(context))


        port = context.current

        LOG.info("PRUTH: bind_port: port" + str(port))

        binding_profile = port['binding:profile']
        local_link_information = binding_profile.get('local_link_information')
        LOG.info("PRUTH: bind_port: 100")
        if self._is_port_supported(port) and local_link_information:
            LOG.info("PRUTH: bind_port: 200")
            switch_info = local_link_information[0].get('switch_info')
            switch_id = local_link_information[0].get('switch_id')
            switch = device_utils.get_switch_device(
                self.switches, switch_info=switch_info,
                ngs_mac_address=switch_id)
            LOG.info("PRUTH: bind_port: 210  switch_info: " + str(switch_info) + ", switch_id: " + str(switch_id) + ", swtich: " + str(switch) + ", switches: " + str(self.switches))
            if not switch:
                return
            LOG.info("PRUTH: bind_port: 220")
            port_id = local_link_information[0].get('port_id')
            segments = context.segments_to_bind
            segmentation_id = segments[0].get('segmentation_id')

            # If segmentation ID is None, set vlan 1
            LOG.info("PRUTH: bind_port: 230")
            if not segmentation_id:
                segmentation_id = '1'
            LOG.info("PRUTH: bind_port: 240")
            provisioning_blocks.add_provisioning_component(
                context._plugin_context, port['id'], resources.PORT,
                GENERIC_SWITCH_ENTITY)
            LOG.info("PRUTH: bind_port: 250")
            LOG.debug("Putting port {port} on {switch_info} to vlan: "
                      "{segmentation_id}".format(
                          port=port_id,
                          switch_info=switch_info,
                          segmentation_id=segmentation_id))
            LOG.info("PRUTH: bind_port: 260: port_id: " + str(port_id) + ", segentation_id: " + str(segmentation_id))
            # Move port to network
            switch.plug_port_to_network(port_id, segmentation_id)
            LOG.info("PRUTH: bind_port: 270")
            LOG.info("Successfully bound port %(port_id)s in segment "
                     " %(segment_id)s on device %(device)s",
                     {'port_id': port['id'], 'device': switch_info,
                      'segment_id': segmentation_id})
            LOG.info("PRUTH: bind_port: 280")
            context.set_binding(segments[0][driver_api.ID],
                                portbindings.VIF_TYPE_OTHER, {})
            LOG.info("PRUTH: bind_port: 999")

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
        switch = device_utils.get_switch_device(
            self.switches, switch_info=switch_info,
            ngs_mac_address=switch_id)
        if not switch:
            return
        port_id = local_link_information[0].get('port_id')
        segmentation_id = network.get('provider:segmentation_id', '1')
        LOG.debug("Unplugging port {port} on {switch_info} from vlan: "
                  "{segmentation_id}".format(
                      port=port_id,
                      switch_info=switch_info,
                      segmentation_id=segmentation_id))
        try:
            switch.delete_port(port_id, segmentation_id)
        except Exception as e:
            LOG.error("Failed to unplug port %(port_id)s "
                      "on device: %(switch)s from network %(net_id)s "
                      "reason: %(exc)s",
                      {'port_id': port['id'], 'net_id': network['id'],
                       'switch': switch_info, 'exc': e})
            raise e
        LOG.info('Port %(port_id)s has been unplugged from network '
                 ' %(net_id)s on device %(device)s',
                 {'port_id': port['id'], 'net_id': network['id'],
                  'device': switch_info})
