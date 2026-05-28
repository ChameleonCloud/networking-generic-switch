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

import re

from oslo_log import log as logging

from networking_generic_switch import exceptions as exc
from networking_generic_switch.devices import netmiko_devices

LOG = logging.getLogger(__name__)


class DellOS10(netmiko_devices.NetmikoSwitch):
    """Netmiko device driver for Dell PowerSwitch switches."""

    ADD_NETWORK = (
        "interface vlan {segmentation_id}",
        "description {network_name}",
        "exit",
    )

    DELETE_NETWORK = (
        "no interface vlan {segmentation_id}",
        "exit",
    )

    PLUG_PORT_TO_NETWORK = (
        "interface {port}",
        "switchport mode access",
        "switchport access vlan {segmentation_id}",
        "exit",
    )

    # Hybrid port mode, untagged access vlan but preserve existing trunks
    PLUG_PORT_TO_NETWORK_TRUNK_NATIVE = (
        "interface {port}",
        "switchport mode trunk",
        "switchport access vlan {segmentation_id}",
        "exit",
    )

    DELETE_PORT = (
        "interface {port}",
        "no switchport access vlan",
        "exit",
    )

    ADD_NETWORK_TO_TRUNK = (
        "interface {port}",
        "switchport mode trunk",
        "switchport trunk allowed vlan {segmentation_id}",
        "exit",
    )

    REMOVE_NETWORK_FROM_TRUNK = (
        "interface {port}",
        "no switchport trunk allowed vlan {segmentation_id}",
        "exit",
    )

    ENABLE_PORT = (
        "interface {port}",
        "no shutdown",
        "exit",
    )

    DISABLE_PORT = (
        "interface {port}",
        "shutdown",
        "exit",
    )

    ERROR_MSG_PATTERNS = (
        re.compile(r'Error:'),
    )
    """Sequence of error message patterns.

    Sequence of re.RegexObject objects representing patterns to check for in
    device output that indicate a failure to apply configuration.
    """

    @netmiko_devices.check_output('plug port')
    def plug_port_to_network(self, port, segmentation_id):
        if port not in self._get_trunk_native_ports():
            return super(DellOS10, self).plug_port_to_network(
                port, segmentation_id)
        LOG.info("Port %s is configured as a trunk-native port; asserting "
                 "trunk mode and setting native vlan %s.",
                 port, segmentation_id)
        cmds = self._format_commands(
            self.PLUG_PORT_TO_NETWORK_TRUNK_NATIVE,
            port=port,
            segmentation_id=segmentation_id)
        return self.send_commands_to_device(cmds)

    @netmiko_devices.check_output('unplug port')
    def delete_port(self, port, segmentation_id):
        if port not in self._get_trunk_native_ports():
            return super(DellOS10, self).delete_port(port, segmentation_id)
        LOG.info("Port %s is configured as a trunk-native port; clearing "
                 "native vlan only, leaving trunk mode and allowed vlans "
                 "intact.", port)
        cmds = self._format_commands(
            self.DELETE_PORT,
            port=port,
            segmentation_id=segmentation_id)
        return self.send_commands_to_device(cmds)


class DellNos(netmiko_devices.NetmikoSwitch):
    """Netmiko device driver for Dell Force10 (OS9) switches."""

    ADD_NETWORK = (
        'interface vlan {segmentation_id}',
        # It's not possible to set the name on OS9: the field takes 32
        # chars max, and cannot begin with a number. Let's set the
        # description and leave the name empty.
        'description {network_name}',
        'exit',
    )

    DELETE_NETWORK = (
        'no interface vlan {segmentation_id}',
        'exit',
    )

    PLUG_PORT_TO_NETWORK = (
        'interface vlan {segmentation_id}',
        'untagged {port}',
        'exit',
    )

    DELETE_PORT = (
        'interface vlan {segmentation_id}',
        'no untagged {port}',
        'exit',
    )

    ADD_NETWORK_TO_TRUNK = (
        'interface vlan {segmentation_id}',
        'tagged {port}',
        'exit',
    )

    REMOVE_NETWORK_FROM_TRUNK = (
        'interface vlan {segmentation_id}',
        'no tagged {port}',
        'exit',
    )

    ERROR_MSG_PATTERNS = (
        re.compile(r'Error:'),
    )


class DellPowerConnect(netmiko_devices.NetmikoSwitch):
    """Netmiko device driver for Dell PowerConnect switches."""

    def _switch_to_general_mode(self):
        self.PLUG_PORT_TO_NETWORK = self.PLUG_PORT_TO_NETWORK_GENERAL
        self.DELETE_PORT = self.DELETE_PORT_GENERAL

    def __init__(self, device_cfg):
        super(DellPowerConnect, self).__init__(device_cfg)
        port_mode = self.ngs_config['ngs_switchport_mode']
        switchport_mode = {
            'general': self._switch_to_general_mode,
            'access': lambda: ()
        }

        def on_invalid_switchmode():
            raise exc.GenericSwitchConfigException(
                option="ngs_switchport_mode",
                allowed_options=switchport_mode.keys()
            )

        switchport_mode.get(port_mode.lower(), on_invalid_switchmode)()

    ADD_NETWORK = (
        'vlan database',
        'vlan {segmentation_id}',
        'exit',
    )

    DELETE_NETWORK = (
        'vlan database',
        'no vlan {segmentation_id}',
        'exit',
    )

    PLUG_PORT_TO_NETWORK_GENERAL = (
        'interface {port}',
        'switchport general allowed vlan add {segmentation_id} untagged',
        'switchport general pvid {segmentation_id}',
        'exit',
    )

    PLUG_PORT_TO_NETWORK = (
        'interface {port}',
        'switchport access vlan {segmentation_id}',
        'exit',
    )

    DELETE_PORT_GENERAL = (
        'interface {port}',
        'switchport general allowed vlan remove {segmentation_id}',
        'no switchport general pvid',
        'exit',
    )

    DELETE_PORT = (
        'interface {port}',
        'switchport access vlan none',
        'exit',
    )

    ADD_NETWORK_TO_TRUNK = (
        'interface {port}',
        'switchport general allowed vlan add {segmentation_id} tagged',
        'exit',
    )

    REMOVE_NETWORK_FROM_TRUNK = (
        'interface {port}',
        'switchport general allowed vlan remove {segmentation_id}',
        'exit',
    )

    ERROR_MSG_PATTERNS = (
        re.compile(r'\% Incomplete command'),
        re.compile(r'VLAN was not created by user'),
        re.compile(r'Configuration Database locked by another application \- '
                   r'try later'),
    )


class DellFNIOA(netmiko_devices.NetmikoSwitch):
    """Netmiko device driver for Dell FN I/O Aggregator switches."""

    PLUG_PORT_TO_NETWORK = (
        'interface {port}',
        'vlan untagged {segmentation_id}'
    )

    DELETE_PORT = (
        'interface {port}',
        'no vlan untagged'
    )
