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

from networking_generic_switch.devices import netmiko_devices
from networking_generic_switch import exceptions as exc

from oslo_log import log as logging
LOG = logging.getLogger(__name__)

class DellNos(netmiko_devices.NetmikoSwitch):
    """Netmiko device driver for Dell Force10 switches."""

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

    QUERY_PORT = (
        'end', # Need to briefly leave configuration mode.
        'show interfaces switchport {port} | grep ^U',
        'conf', # Re-enter configuration mode.
    )

    QUERY_PORT_REGEX = re.compile(r'^U\s+(\d+)', re.MULTILINE)

    ERROR_MSG_PATTERNS = (
        re.compile(r'Port is untagged in another Vlan'),
    )

    @netmiko_devices.check_output('plug port')
    def plug_port_to_network(self, port, segmentation_id):
        show_port_output = self.send_commands_to_device(
            self._format_commands(self.QUERY_PORT, port=port))
        matches = re.findall(self.QUERY_PORT_REGEX, show_port_output)
        current_vlan = matches[0] if matches else None

        # NOTE(diurnalist): ports are implicitly assigned to VLAN 1
        # when all VLAN tags are removed from them.
        if (current_vlan and current_vlan not in ['1', str(segmentation_id)]):
            LOG.warning(('Port {port} is used in VLAN {vlan}, '
                         'attempting to clean it.'.format(port=port,
                                                          vlan=current_vlan)))
            cmds = self._format_commands(self.DELETE_PORT,
                                         port=port,
                                         segmentation_id=current_vlan)
            cmds += self._format_commands(self.PLUG_PORT_TO_NETWORK,
                                          port=port,
                                          segmentation_id=segmentation_id)
            self.send_commands_to_device(cmds)
        else:
            super(DellNos, self).plug_port_to_network(port, segmentation_id)


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
