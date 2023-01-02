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
import traceback
import pprint

#import res

from networking_generic_switch import config as gsw_conf
from networking_generic_switch import devices
from networking_generic_switch.devices import utils as device_utils

from neutron.objects import ports as port_obj
from neutron.objects import network as network_obj
from neutron_lib import context as lib_context

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

        #logging.basicConfig(format='%(levelname)s:%(threadName)s:%(message)s', level=logging.DEBUG)

        self.vfcHost = None
        gsw_devices = gsw_conf.get_devices()
        self.switches = {}

        self.haswellNodeRange=(201,299)

        self.stitching_shadow_network_name = None
        self.stitching_shadow_network_id = None
        self.stitching_shadow_network = None
        self.patchpanel_switch = None
        self.patchpanel_port_map = {}
        #self.patch_vlans_available = []
        self.patch_vlans = {}

        #TEST
        LOG.debug("XXXXXXXXXXXXXXXXXXXXXXXX PRINTIGN SWITCHES  XXXXXXXXXXXXXX")

        for switch_name, switch in gsw_devices.items():
            LOG.debug("XXXXXXXXXXXXXXXXXXXXXXXX SWITCH " + str(switch_name) + " XXXXXXXXXXXXXX")
            LOG.debug(str(switch))



        try:
            LOG.info("stitching_shadow_network: " + str(CONF.ngs_coordination.stitching_shadow_network))
            self.stitching_shadow_network_name = CONF.ngs_coordination.stitching_shadow_network
        except:
            LOG.info("stitching_shadow_network undefined")

        try:
            LOG.info("patchpanel_switch: " + str(CONF.ngs_coordination.patchpanel_switch))
            self.patchpanel_switch_name = CONF.ngs_coordination.patchpanel_switch

            self.__get_shadow_network()
            #self.__get_patchpanel_switch()
            #self.__init_patch_vlans()

            LOG.info("port_map: " + str(CONF.ngs_coordination.patchpanel_port_map))
            self.patchpanel_port_map = {}
            for port_str in CONF.ngs_coordination.patchpanel_port_map.split(','):
                port_name, port_id = port_str.split(":")
                LOG.info("port_map adding: " + str(port_name) + ", " + str(port_id))
                self.patchpanel_port_map[port_name] = port_id

            LOG.info("port_map built: " + str(self.patchpanel_port_map ))
        except Exception as e:
            import traceback
            LOG.info("patchpanel_switch undefined" + str(traceback.format_exc()))

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

    def __is_shadow_network(self, context):
        network = context.current
        network_id = network['id']
        LOG.debug("network: " + str(network) + ", network_id: " + str(network_id))

        if self.stitching_shadow_network_name and self.stitching_shadow_network_name == network['name']:
            LOG.debug("Setting new stitching_shadow_network")
            self.stitching_shadow_network = network

        if self.stitching_shadow_network and network['id'] == self.stitching_shadow_network['id']:
            LOG.debug('adding to shadow network. no physical config required')
            return True
        else:
            return False


    def __is_authorized(self, context):
        # TODO: Write authorization check
        return True

    def create_network_precommit(self, context):
        """Allocate resources for a new network.

        :param context: NetworkContext instance describing the new
        network.

        Create a new network, allocating resources as necessary in the
        database. Called inside transaction context on session. Call
        cannot block.  Raising an exception will result in a rollback
        of the current transaction.
        """
        network = context.current
        provider = network['provider:physical_network']
        description = network['description']

        # Add authorization of SDN network creation (i.e. corsa vfcs).
        # Reject early if not authorization.
        if provider == 'user':
            LOG.info("Authorizing create user controlled network: provider: " + str(provider) +
                     ", description: " + str(description))
            LOG.info("Skipping authorization...")
            if not self.__is_authorized(context):
                LOG.error("create_network_precommit failed authorization")
                raise Exception("not authorized to create network")

    def create_network_postcommit(self, context):
        """Create a network.

        :param context: NetworkContext instance describing the new
        network.

        Called after the transaction commits. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance. Raising an exception will
        cause the deletion of the resource.
        """

        LOG.debug("create_network_postcommit")

        network = context.current
        network_id = network['id']
        project_id = network['project_id'].strip()
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']
        physnet = network['provider:physical_network']

        if self.__is_shadow_network(context):
            LOG.info("Creating shadow network: " + str(network))
            return

        LOG.debug("network: " + str(network) + ", network_id: " + str(network_id))

        if provider_type == 'vlan' and segmentation_id:
            # Create vlan on all switches from this driver
            for switch_name, switch in self._get_devices_by_physnet(physnet):
                # Skip configuring the patchpanel for regular networks
                if hasattr(self, 'patchpanel_switch_name') and switch_name == self.patchpanel_switch_name:
                    LOG.debug("Skipping patchpanel switch config for new networks")
                    continue

                if physnet == 'user':
                    # Create user controlled network
                    of_controller = self.__get_of_controller(network)
                    vfc_name = self.__get_vfc_name(network, project_id)
                    if hasattr(devices, 'corsa_devices') and isinstance(switch, devices.corsa_devices.corsa2100.CorsaDP2100):
                        LOG.info("Creating corsa vfc network")
                        switch.add_network(segmentation_id, network_id, project_id, of_controller, vfc_name)
                    continue

                # Create standard network
                LOG.info("Creating standard network" )
                switch.add_network(segmentation_id, network_id)

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

        network = context.current
        provider = network['provider:physical_network']
        description = network['description']

        # Add authorization of SDN network creation (i.e. corsa vfcs).
        # Reject early if not authorization.
        if provider == 'user':
            LOG.info("Authorizing update user controlled network: provider: " + str(provider) +
                     ", description: " + str(description))
            LOG.info("Skipping authorization...")
            if not self.__is_authorized(context):
                LOG.error("update_network_precommit failed authorization")
                raise Exception("not authorized to update network")


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

        network = context.current
        provider = network['provider:physical_network']
        description = network['description']

        # Add authorization of SDN network creation (i.e. corsa vfcs).
        # Reject early if not authorization.
        if provider == 'user':
            LOG.info("Authorizing delete user controlled network: provider: " + str(provider) +
                     ", description: " + str(description))
            LOG.info("Skipping authorization...")
            if not self.__is_authorized(context):
                LOG.error("delete_network_precommit failed authorization")
                raise Exception("not authorized to delete network")



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

        if self.stitching_shadow_network != None and network['id'] == self.stitching_shadow_network['id']:
            LOG.debug('deleting shadow network. no physical config required')
            return

        if provider_type == 'vlan' and segmentation_id:
            # Delete vlan on all switches from this driver
            for switch_name, switch in self._get_devices_by_physnet(physnet):
                # Skip configuring the patchpanel for regular networks
                if hasattr(self, 'patchpanel_switch_name') and switch_name == self.patchpanel_switch_name:
                    LOG.debug("Skipping patchpanel switch config for vlan network")
                    continue

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

        network = context.network.current
        provider = network['provider:physical_network']

        # Add authorization of SDN network creation (i.e. corsa vfcs).
        # Reject early if not authorization.
        if provider == 'user':
            LOG.error("User controlled networks require manual configuration of subnets and IPs")
            raise Exception("User controlled networks require manual configuration of subnets and IPs")


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

        network = context.network.current
        provider = network['provider:physical_network']
        description = network['description']

        # Add authorization of SDN network creation (i.e. corsa vfcs).
        # Reject early if not authorization.
        if provider == 'user':
            LOG.info("Authorizing create port on user controlled network: provider: " + str(provider) +
                     ", description: " + str(description))
            LOG.info("Skipping authorization...")
            if not self.__is_authorized(context):
                LOG.error("create_port_precommit failed authorization")
                raise Exception("not authorized to create port")


    def __get_shadow_port(self, port):
        from neutron.objects.ports import Port

        from neutron.objects import tag as tag_obj
        from neutron_lib.plugins import directory

        if self.stitching_shadow_network_name == None:
            LOG.debug("Shadow port not set, skipping")
            return None

        if self.stitching_shadow_network == None:
            self.stitching_shadow_network = self.__get_shadow_network()

        if self.stitching_shadow_network == None:
            LOG.debug("No shadow network, skipping")
            return None

        if port['network_id'] == self.stitching_shadow_network['id']:
            LOG.debug("Port is shadow port, skipping")
            return None

        LOG.debug("XXXXXX self.stitching_shadow_network: " + str(self.stitching_shadow_network))
        LOG.debug("XXXXXX self.stitching_shadow_network['id']: " + str(self.stitching_shadow_network['id']))
        LOG.debug("XXXXXX port['network_id']: " + str(port['network_id']))


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

        #port = context.current  # NOW passed in
        port_id = port['id']

        LOG.debug("port: " + str(port))
        # network_id = port['network_id']

        # LOG.debug("create_port_postcommit: port_id: " + str(port_id) + ", network_id: " + str(network_id))

        # admin_context = lib_context.get_admin_context()
        # network = network_obj.Network.get_objects(admin_context,id=network_id)[0]

        LOG.debug("Port \n" + pprint.pformat(port, indent=4) + "\n")
        LOG.debug("port[binding:profile] \n" + pprint.pformat(port['binding:profile'], indent=4) + "\n")

        for k,v in port['binding:profile'].items():
            LOG.debug("key: " + str(k) + ", val: " + str(v))



        port_type = None
        shadow_port = None
        if 'type' in port['binding:profile']:
            port_type = port['binding:profile']['type']
            project_id = port['project_id']
            if 'reservation_id' in port['binding:profile']:
                reservation_id = port['binding:profile']['reservation_id']



            if port_type == 'stitchport':
                LOG.debug('Adding stitch port: port_type: ' + str(port_type))
                LOG.debug('patchpanel_port_map:  ' + str(self.patchpanel_port_map))

            LOG.debug("Searching for shadow port, ")
            for shadow_port_candidate in port_obj.Port.get_objects(admin_context):
                try:
                    if self.stitching_shadow_network != None and shadow_port_candidate['network_id'] != self.stitching_shadow_network['id']:
                        LOG.debug("Skipping non-shadow network port")
                        continue

                    LOG.debug("Candidate shadow_port: " + str(shadow_port_candidate))

                    binding = None
                    for binding_candidate in shadow_port_candidate['bindings']:
                        LOG.debug("shadow_port_candidate['bindings'] type: " + str(type(binding_candidate)))
                        LOG.debug("shadow_port_candidate['bindings'] binding: " + str(binding_candidate))

                    shadow_port_candidate_binding_profile = shadow_port_candidate['bindings'][0]['profile']

                    LOG.debug("\n" + "project_id " + str(project_id) + "\n" +
                              "reservation_id " + str(reservation_id) + "\n" +
                              "shadow_port_candidate['project_id'] " + str(shadow_port_candidate['project_id']) + "\n" +
                              "shadow_port_candidate_binding_profile['reservation_id'] " + str(shadow_port_candidate_binding_profile['reservation_id']) + "\n" )

                    if shadow_port_candidate['project_id'] == project_id and \
                       shadow_port_candidate_binding_profile['reservation_id'] == reservation_id:
                        shadow_port = shadow_port_candidate
                        #LOG.debug("Found shadow stitchport: \n" + pprint.pformat(shadow_port, indent=4) + "\n")
                        #json.dumps(str(context.__dict__
                        LOG.debug("Found shadow stitchport: \n" + pprint.pformat(shadow_port.__dict__, indent=4) + "\n")



                        break
                except Exception as e:
                    LOG.debug("Exception in testing shadow_port_candidate: " + str(e)  + ", " + str(traceback.format_exc()) + ", shadow_port_candidate: " + str(shadow_port_candidate))
                    continue

        if shadow_port == None:
            LOG.debug("shadow stitchport not found!")

        return shadow_port

    def __get_shadow_network(self):
        admin_context = lib_context.get_admin_context()
        LOG.debug("__get_shadow_network: name: " + self.stitching_shadow_network_name)
        nets = network_obj.Network.get_objects(admin_context, name=self.stitching_shadow_network_name)
        LOG.debug("Nets: " + str(nets))
        if len(nets) == 1:
            net = nets[0]
            LOG.debug("Net: " + str(net))
            if str(net['name']) == self.stitching_shadow_network_name:
                LOG.debug("FOUND SHADOW STITCH NETWORK: " + str(net['name']) + ", " + str(net))
                self.stitching_shadow_network = net
        elif len(nets) < 1:
            LOG.debug("No shadow network ")
            self.stitching_shadow_network = None
        else:
            raise Exception("More than one network with shadow network name: " + str(nets))

        return self.stitching_shadow_network


    def __get_shadow_network_id(self):

        LOG.debug("__get_shadow_network_id: self.stitching_shadow_network_name: " + str(self.stitching_shadow_network_name))
        admin_context = lib_context.get_admin_context()

        for network in network_obj.Network.get_objects(admin_context):
            LOG.debug("network: " + str(network))
            if network['name'] == self.stitching_shadow_network_name:
                LOG.debug("FOUND: stitching_shadow_network: " + str(network))
                self.stitching_shadow_network_id = network['id']
                return self.stitching_shadow_network_id

        LOG.debug("NOT FOUND: stitching_shadow_network: returning None")
        return None

    def __init_patch_vlans(self):
        admin_context = lib_context.get_admin_context()

        # Create the list of available patch panel VLANs from the config file
        LOG.info("Initiating patch_vlans:  patch vlans: " + str(CONF.ngs_coordination.patch_vlans))
        self.patch_vlans_available = []
        [self.patch_vlan_low, self.patch_vlan_high] = CONF.ngs_coordination.patch_vlans.split(':')
        for vlan in range(int(self.patch_vlan_low), int(self.patch_vlan_high) + 1):
            self.patch_vlans_available.append(str(vlan))

        # Remove vlans allocated to networks
        if not self.stitching_shadow_network_id:
            self.stitching_shadow_network_id == self.__get_shadow_network_id()

        LOG.debug("stitching_shadow_network_id: " + str(self.stitching_shadow_network_id))

        for port in port_obj.Port.get_objects(admin_context):
            try:
                LOG.debug("port: " + str(port))

                port_binding_profile = port['bindings'][0]['profile']

                LOG.debug("\n Stitchport vlan: " + str(port_binding_profile['stitch_vlan']) + "\n")

                if 'patch_vlan' in port_binding_profile:
                    patch_vlan = port_binding_profile['patch_vlan']
                    LOG.debug("Patch vlan: " + str(patch_vlan))
                    try:
                        if str(patch_vlan) in self.patch_vlans:
                            self.patch_vlans[str(patch_vlan)]['ports'].append(port['id'])
                        else:
                            self.patch_vlans[str(patch_vlan)] = { 'name': 'p'+str(patch_vlan),
                                                                  'ports': [ port['id'] ] }
                    except Exception as e:
                        LOG.warning("Failed to remove patch vlan from init list. " +
                                    "Likely reason is duplicate patch vlan assignment. " +
                                    "patch_vlan: " + str(patch_vlan) + "\n" +
                                    "Exception: " + str(traceback.format_exc()))
            except Exception as e:
                LOG.debug("Exception initiating patch_vlan: " + str(e) + ", " + str(
                    traceback.format_exc()) + ", patch_vlan: " + str(patch_vlan))
                raise e


        LOG.debug("patch_vlans: \n" + pprint.pformat(self.patch_vlans, indent=4) + "\n" )

    # def __init_patch_vlans(self):
    #     admin_context = lib_context.get_admin_context()
    #
    #     # Create the list of available patch panel VLANs from the config file
    #     LOG.info("Initiating patch_vlans:  patch vlans: " + str(CONF.ngs_coordination.patch_vlans))
    #     self.patch_vlans_available = []
    #     [patch_vlan_low, patch_vlan_high] = CONF.ngs_coordination.patch_vlans.split(':')
    #     for vlan in range(int(patch_vlan_low), int(patch_vlan_high) + 1):
    #         self.patch_vlans_available.append(str(vlan))
    #
    #     # Remove vlans allocated to networks
    #     if not self.stitching_shadow_network_id:
    #         self.stitching_shadow_network_id == self.__get_shadow_network_id()
    #
    #     LOG.debug("stitching_shadow_network_id: " + str(self.stitching_shadow_network_id))
    #
    #     for port in port_obj.Port.get_objects(admin_context, network_id=self.stitching_shadow_network_id):
    #         try:
    #             LOG.debug("Stitching port: " + str(port))
    #
    #             port_binding_profile = port['bindings'][0]['profile']
    #
    #             LOG.debug("\n Stitchport vlan: " + str(port_binding_profile['stitch_vlan']) + "\n")
    #
    #             if 'patch_vlan' in port_binding_profile:
    #                 patch_vlan = port_binding_profile['patch_vlan']
    #                 LOG.debug("Patch vlan: " + str(patch_vlan))
    #                 try:
    #                     self.patch_vlans_available.remove(str(patch_vlan))
    #                 except Exception as e:
    #                     LOG.warning("Failed to remove patch vlan from init list. " +
    #                                 "Likely reason is duplicate patch vlan assignment. " +
    #                                 "patch_vlan: " + str(patch_vlan) + "\n" +
    #                                 "Exception: " + str(traceback.format_exc()))
    #         except Exception as e:
    #             LOG.debug("Exception initiating patch_vlan: " + str(e) + ", " + str(
    #                 traceback.format_exc()) + ", patch_vlan: " + str(patch_vlan))
    #             raise e

    def __release_patch_vlan(self, vlan=None):
        LOG.info("Releasing patch vlan " + str(vlan))
        if vlan:
            self.patch_vlans_available.append(str(vlan))
        else:
            LOG.warning("Cannot release patch vlan: " + str(vlan))

    def __allocate_patch_vlan(self, avoid_vlans=[]):
        self.__init_patch_vlans()

        for patch_vlan in self.patch_vlans_available:
            if patch_vlan not in avoid_vlans:
                self.patch_vlans_available.remove(patch_vlan)
                break
            else:
                LOG.info("Allocated patch vlan conflict... retry:  " + str(patch_vlan))

        LOG.info("Allocated patch vlan " + str(patch_vlan))

        return patch_vlan

    def __get_patchpanel_switch(self):
        LOG.info("Getting patchpanel")
        admin_context = lib_context.get_admin_context()
        LOG.debug("admin_context, " + str(admin_context))

        try:
            # Find the patch panel switch object
            for switch_name, switch in self.switches.items():
                LOG.debug("Searching for patchpanel switch (" + self.patchpanel_switch_name + ". candidate: " + str(
                    switch_name))
                if switch_name == self.patchpanel_switch_name:
                    self.patchpanel_switch = switch
                    break

            # Create the map of patch panel ports to destinations
            LOG.info("port_map: " + str(CONF.ngs_coordination.patchpanel_port_map))
            self.patchpanel_port_map = {}
            for port_str in CONF.ngs_coordination.patchpanel_port_map.split(','):
                port_name, port_id = port_str.split(":")
                LOG.info("port_map adding: " + str(port_name) + ", " + str(port_id))
                self.patchpanel_port_map[port_name] = port_id
            LOG.info("port_map built: " + str(self.patchpanel_port_map ))
            LOG.debug('Patch VLANs: ' + str(self.patch_vlans_available))
        except Exception as e:
            import traceback
            LOG.info("patchpanel_switch undefined" + str(traceback.format_exc()))

        return self.patchpanel_switch

    def create_port_postcommit(self, context):
        """Create a port.

        :param context: PortContext instance describing the port.

        Called after the transaction completes. Call can block, though
        will block the entire process so care should be taken to not
        drastically affect performance.  Raising an exception will
        result in the deletion of the resource.
        """
        LOG.debug("create_port_postcommit \n" + pprint.pformat(context.current, indent=4) + "\n")

        port = context.current
        shadow_port = self.__get_shadow_port(port)

        LOG.debug("shadow_port: " + str(shadow_port))
        if shadow_port and shadow_port.bindings:
            LOG.debug("bindings: " + str(shadow_port.bindings))
            LOG.debug("profile: \n" + pprint.pformat(shadow_port.bindings[0]['profile']) + "/n")
            for k, v in shadow_port.bindings[0]['profile'].items():
                LOG.debug("" + str(k) + ", " + str(v))
        else:
            LOG.debug("bindings: NO binding profile")

        self.__get_patchpanel_switch()



        network = context.network.current
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']
        physnet = network['provider:physical_network']

        if shadow_port:
            shadow_port_binding = shadow_port['bindings'][0]
            shadow_port_binding_profile = shadow_port_binding['profile']
            port_type = port['binding:profile']['type']

            LOG.debug('Adding port with shadowport: port_type: ' + str(port_type))
            LOG.debug('patchpanel_port_map:  ' + str(self.patchpanel_port_map))

            if 'reservation_id' in port['binding:profile']:
                reservation_id = port['binding:profile']['reservation_id']

            #get shadow vlan and stitchport from shadow port
            stichport_name = shadow_port_binding_profile['stitchport']
            stichport_vlan = shadow_port_binding_profile['stitch_vlan']
            LOG.debug('stichport_name: ' + str(stichport_name) + ", stichport_vlan: " + str(stichport_vlan))

            # Add patch
            try:
                port1_name = self.patchpanel_port_map[stichport_name]
                port1_vlan = stichport_vlan
                port2_name = self.patchpanel_port_map[physnet]
                port2_vlan = segmentation_id
                patch_vlan = self.__allocate_patch_vlan(avoid_vlans=[str(port1_vlan),str(port2_vlan)])

                LOG.info('Adding patch: ' + str(self.patchpanel_switch) + "\n" +
                         ', patch_vlan: ' + str(patch_vlan) + "\n" +
                         ', port1_name: ' + str(port1_name) + "\n" +
                         ', port1_vlan: ' + str(port1_vlan) + "\n" +
                         ', port2_name: ' + str(port2_name) + "\n" +
                         ', port2_vlan: ' + str(port2_vlan) + "\n"
                         )

                # Update shadow port binding profile
                shadow_port_binding = shadow_port['bindings'][0]
                new_shadow_binding_profile = {}
                for k, v in shadow_port_binding_profile.items():
                    new_shadow_binding_profile[k] = v

                new_shadow_binding_profile['patch_vlan'] = patch_vlan
                new_shadow_binding_profile['user_port_id'] = port['id']
                shadow_port_binding.profile = new_shadow_binding_profile
                shadow_port_binding.update()

                # Update user port binding profile
                #user_port_binding = port['bindings'][0]
                #new_user_port_binding_profile = {}
                #for k, v in user_port_binding.items():
                #    new_user_port_binding_profile[k] = v

                #new_user_port_binding_profile['stitchport'] = new_shadow_binding_profile['stitchport']
                #new_user_port_binding_profile['stitch_vlan'] = new_shadow_binding_profile['stitch_vlan']
                #user_port_binding.profile = new_user_port_binding_profile
                #user_port_binding.update()

                self.patchpanel_switch.add_patch(patch_id=patch_vlan,
                                 port1_name=port1_name,
                                 port1_vlan=port1_vlan,
                                 port2_name=port2_name,
                                 port2_vlan=port2_vlan)



            except Exception as e:
                LOG.error(str(e) + ", traceback: " + str(traceback.format_exc()))
                raise e

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
                    LOG.error("Failed to crete port %(port)s "
                              "on device: %(switch)s, reason: %(exc)s",
                              {'port_id': port['id'],
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

        network = context.network.current
        provider = network['provider:physical_network']
        description = network['description']

        # Add authorization of SDN network creation (i.e. corsa vfcs).
        # Reject early if not authorization.
        if provider == 'user':
            LOG.info("Authorizing create port on user controlled network: provider: " + str(provider) +
                     ", description: " + str(description))
            LOG.info("Skipping authorization...")
            if not self.__is_authorized(context):
                LOG.error("update_port_precommit failed authorization")
                raise Exception("not authorized to update port")


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
        network = context.network.current
        provider = network['provider:physical_network']
        description = network['description']

        port = context.current
        shadow_port = self.__get_shadow_port(port)

        LOG.debug("shadow_port: " + str(shadow_port))
        if shadow_port and shadow_port.bindings:
            LOG.debug("bindings: " + str(shadow_port.bindings))
            LOG.debug("profile: \n" + pprint.pformat(shadow_port.bindings[0]['profile']) + "/n")
            for k, v in shadow_port.bindings[0]['profile'].items():
                LOG.debug("" + str(k) + ", " + str(v))
        else:
            LOG.debug("bindings: NO binding profile")


        # Add authorization of SDN network creation (i.e. corsa vfcs).
        # Reject early if not authorization.
        if provider == 'user':
            LOG.info("Authorizing delete port on user controlled network: provider: " + str(provider) +
                     ", description: " + str(description))
            LOG.info("Skipping authorization...")
            if not self.__is_authorized(context):
                LOG.error("delete_port_precommit failed authorization")
                raise Exception("not authorized to delete port")

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
        LOG.debug("" + json.dumps(str(context.__dict__), indent=2))
        LOG.debug("" + str(context.current))

        port = context.current
        shadow_port = self.__get_shadow_port(port)

        self.__get_patchpanel_switch()


        network = context.network.current
        provider_type = network['provider:network_type']
        segmentation_id = network['provider:segmentation_id']
        physnet = network['provider:physical_network']

        if shadow_port:
            shadow_port_binding_profile = shadow_port['bindings'][0]['profile']
            port_type = port['binding:profile']['type']

            LOG.debug('Adding port with shadowport: port_type: ' + str(port_type))
            LOG.debug('patchpanel_port_map:  ' + str(self.patchpanel_port_map))

            if 'reservation_id' in port['binding:profile']:
                reservation_id = port['binding:profile']['reservation_id']

            #get shadow vlan and stitchport from shadow port
            stichport_name = shadow_port_binding_profile['stitchport']
            stichport_vlan = shadow_port_binding_profile['stitch_vlan']
            LOG.debug('stichport_name: ' + str(stichport_name) + ", stichport_vlan: " + str(stichport_vlan))

            try:
                port1_name = self.patchpanel_port_map[stichport_name]
                port1_vlan = stichport_vlan
                port2_name = self.patchpanel_port_map[physnet]
                port2_vlan = segmentation_id

                #patch = self.patch_vlans_allocated.pop(port['id']) #TODO: roll back on failure. This might leak patch vlans
                patch_vlan = shadow_port_binding_profile['patch_vlan']
                LOG.debug('Deleting patch: ' + str(self.patchpanel_switch) +
                          ', port1_name: ' + str(port1_name) +
                          ', port1_vlan: ' + str(port1_vlan) +
                          ', port2_name: ' + str(port2_name) +
                          ', port2_vlan: ' + str(port2_vlan)
                          )

                self.patchpanel_switch.remove_patch(patch_id=patch_vlan)

                # Upade shadow port binding info
                shadow_port_binding = shadow_port['bindings'][0]
                new_binding_profile = {}
                for k, v in shadow_port_binding_profile.items():
                    new_binding_profile[k] = v
                new_binding_profile.pop('patch_vlan')
                new_binding_profile.pop('user_port_id')
                shadow_port_binding.profile = new_binding_profile
                shadow_port_binding.update()

                #self.__release_patch_vlan(vlan=patch_vlan)

            except Exception as e:
                import traceback
                LOG.error(str(e) + ", traceback: " + str(traceback.format_exc()))
        else:
            # Non-patch panel
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
