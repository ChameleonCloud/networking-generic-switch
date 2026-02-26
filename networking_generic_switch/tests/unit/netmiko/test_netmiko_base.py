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
from unittest import mock

import fixtures
import netmiko
import netmiko.base_connection
from oslo_config import fixture as config_fixture
import paramiko
import tenacity
from tooz import coordination

from networking_generic_switch import batching
from networking_generic_switch.devices import netmiko_devices
from networking_generic_switch.devices import utils
from networking_generic_switch import exceptions as exc


class NetmikoSwitchTestBase(fixtures.TestWithFixtures):
    def setUp(self):
        super(NetmikoSwitchTestBase, self).setUp()
        self.cfg = self.useFixture(config_fixture.Config())
        self.switch = self._make_switch_device()

    def _make_switch_device(self, extra_cfg={}):
        patcher = mock.patch.object(
            netmiko_devices.netmiko, 'platforms', new=['base'])
        patcher.start()
        self.addCleanup(patcher.stop)
        device_cfg = {'device_type': 'netmiko_base',
                      'ip': 'host'}
        device_cfg.update(extra_cfg)
        return netmiko_devices.NetmikoSwitch(device_cfg)


class TestNetmikoSwitch(NetmikoSwitchTestBase):

    def test_batch(self):
        self.cfg.config(backend_url='url', group='ngs_coordination')
        self._make_switch_device({'ngs_batch_requests': True})

    def test_batch_missing_backend_url(self):
        self.assertRaisesRegex(
            Exception, "backend_url",
            self._make_switch_device, {'ngs_batch_requests': True})

    @mock.patch.object(netmiko, 'ConnectHandler')
    def test_batch_reuses_connection_across_subsequent_batches(
            self, m_conn_handler):
        self.cfg.config(backend_url='url', group='ngs_coordination')
        switch = self._make_switch_device({
            'ngs_batch_requests': True,
            'ngs_ssh_reuse_connection': True,
        })
        switch.batch_cmds = batching.SwitchBatch(
            switch_name='host', switch_queue=mock.Mock())
        connection = mock.MagicMock(netmiko.base_connection.BaseConnection)
        m_conn_handler.return_value = connection

        lock = mock.MagicMock()
        switch.batch_cmds._send_commands(switch, [{'cmds': ['cmd1']}], lock)
        switch.batch_cmds._send_commands(switch, [{'cmds': ['cmd2']}], lock)

        self.assertEqual(1, m_conn_handler.call_count)

    @mock.patch.object(netmiko, 'ConnectHandler')
    def test_batch_replaces_dead_connection_across_subsequent_batches(
            self, m_conn_handler):
        self.cfg.config(backend_url='url', group='ngs_coordination')
        switch = self._make_switch_device({
            'ngs_batch_requests': True,
            'ngs_ssh_reuse_connection': True,
        })
        switch.batch_cmds = batching.SwitchBatch(
            switch_name='host', switch_queue=mock.Mock())
        first_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        second_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        first_connection.is_alive.return_value = False
        m_conn_handler.side_effect = [first_connection, second_connection]

        lock = mock.MagicMock()
        switch.batch_cmds._send_commands(switch, [{'cmds': ['cmd1']}], lock)
        switch.batch_cmds._send_commands(switch, [{'cmds': ['cmd2']}], lock)

        self.assertEqual(2, m_conn_handler.call_count)
        first_connection.disconnect.assert_called_once_with()
        second_connection.disconnect.assert_not_called()

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_add_network(self, m_check, m_sctd):
        self.switch.add_network(22, '0ae071f5-5be9-43e4-80ea-e41fefe85b21')
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'add network')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_add_network_with_trunk_ports(self, m_check, m_sctd):
        switch = self._make_switch_device({'ngs_trunk_ports': 'port1, port2'})
        switch.add_network(22, '0ae071f5-5be9-43e4-80ea-e41fefe85b21')
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'add network')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_add_network_with_no_manage_vlans(self, m_check, m_sctd):
        switch = self._make_switch_device({'ngs_manage_vlans': False})
        switch.add_network(22, '0ae071f5-5be9-43e4-80ea-e41fefe85b21')
        self.assertFalse(m_sctd.called)
        m_check.assert_called_once_with('', 'add network')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_del_network(self, m_check, m_sctd):
        self.switch.del_network(22, '0ae071f5-5be9-43e4-80ea-e41fefe85b21')
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'delete network')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_del_network_with_trunk_ports(self, m_check, m_sctd):
        switch = self._make_switch_device({'ngs_trunk_ports': 'port1, port2'})
        switch.del_network(22, '0ae071f5-5be9-43e4-80ea-e41fefe85b21')
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'delete network')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_del_network_with_no_manage_vlans(self, m_check, m_sctd):
        switch = self._make_switch_device({'ngs_manage_vlans': False})
        switch.del_network(22, '0ae071f5-5be9-43e4-80ea-e41fefe85b21')
        self.assertFalse(m_sctd.called)
        m_check.assert_called_once_with('', 'delete network')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_plug_port_to_network(self, m_check, m_sctd):
        self.switch.plug_port_to_network(2222, 22)
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'plug port')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_plug_port_has_default_vlan(self, m_check, m_sctd):
        switch = self._make_switch_device({'ngs_port_default_vlan': '20'})
        switch.plug_port_to_network(2222, 22)
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'plug port')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_plug_port_to_network_disable_inactive(self, m_check, m_sctd):
        switch = self._make_switch_device(
            {'ngs_disable_inactive_ports': 'true'})
        switch.plug_port_to_network(2222, 22)
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'plug port')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_delete_port(self, m_check, m_sctd):
        self.switch.delete_port(2222, 22)
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'unplug port')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_delete_port_has_default_vlan(self, m_check, m_sctd):
        switch = self._make_switch_device({'ngs_port_default_vlan': '20'})
        switch.delete_port(2222, 22)
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'unplug port')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.send_commands_to_device',
                return_value='fake output')
    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.check_output')
    def test_delete_port_disable_inactive(self, m_check, m_sctd):
        switch = self._make_switch_device(
            {'ngs_disable_inactive_ports': 'true'})
        switch.delete_port(2222, 22)
        m_sctd.assert_called_with([])
        m_check.assert_called_once_with('fake output', 'unplug port')

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.plug_port_to_network',
                return_value='fake output')
    def test_plug_bond_to_network_fallback(self, m_plug):
        self.switch.plug_bond_to_network(2222, 22)
        m_plug.assert_called_with(2222, 22)

    @mock.patch('networking_generic_switch.devices.netmiko_devices.'
                'NetmikoSwitch.delete_port',
                return_value='fake output')
    def test_unplug_bond_from_network_fallback(self, m_delete):
        self.switch.unplug_bond_from_network(2222, 22)
        m_delete.assert_called_with(2222, 22)

    def test__format_commands(self):
        self.switch._format_commands(
            netmiko_devices.NetmikoSwitch.ADD_NETWORK,
            segmentation_id=22, network_id=22)

    @mock.patch.object(netmiko_devices.tenacity, 'wait_fixed',
                       return_value=tenacity.wait_fixed(0.01))
    @mock.patch.object(netmiko_devices.tenacity, 'stop_after_delay',
                       return_value=tenacity.stop_after_delay(0.1))
    @mock.patch.object(netmiko, 'ConnectHandler')
    def test__get_connection_connect_fail(self, m_conn_handler,
                                          m_stop, m_wait):
        m_conn = mock.MagicMock()
        m_conn_handler.side_effect = [
            paramiko.SSHException, m_conn]
        with self.switch._get_connection() as conn:
            self.assertEqual(conn, m_conn)
        m_stop.assert_called_once_with(60)
        m_wait.assert_called_once_with(10)

    @mock.patch.object(netmiko_devices.tenacity, 'wait_fixed',
                       return_value=tenacity.wait_fixed(0.01))
    @mock.patch.object(netmiko_devices.tenacity, 'stop_after_delay',
                       return_value=tenacity.stop_after_delay(0.1))
    @mock.patch.object(netmiko, 'ConnectHandler')
    def test__get_connection_timeout(self, m_conn_handler, m_stop, m_wait):
        switch = self._make_switch_device({'ngs_ssh_connect_timeout': '1',
                                           'ngs_ssh_connect_interval': '1'})
        m_conn_handler.side_effect = (
            paramiko.SSHException)

        def get_connection():
            with switch._get_connection():
                self.fail()

        self.assertRaises(exc.GenericSwitchNetmikoConnectError, get_connection)
        m_stop.assert_called_once_with(1)
        m_wait.assert_called_once_with(1)

    @mock.patch.object(netmiko_devices.tenacity, 'wait_fixed',
                       return_value=tenacity.wait_fixed(0.01))
    @mock.patch.object(netmiko_devices.tenacity, 'stop_after_delay',
                       return_value=tenacity.stop_after_delay(0.1))
    @mock.patch.object(netmiko, 'ConnectHandler')
    def test__get_connection_caller_failure(self, m_conn_handler,
                                            m_stop, m_wait):
        m_conn = mock.MagicMock()
        m_conn_handler.return_value = m_conn

        class FakeError(Exception):
            pass

        def get_connection():
            with self.switch._get_connection():
                raise FakeError()

        self.assertRaises(FakeError, get_connection)
        m_conn.__exit__.assert_called_once_with(mock.ANY, mock.ANY, mock.ANY)

    @mock.patch.object(netmiko, 'ConnectHandler')
    def test__get_connection_returns_to_pool(self, m_conn_handler):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        m_conn = mock.MagicMock(netmiko.base_connection.BaseConnection)
        m_conn_handler.return_value = m_conn

        with switch._get_connection() as conn:
            self.assertEqual(conn, m_conn)
        m_conn.disconnect.assert_not_called()

        with switch._get_connection() as conn:
            self.assertEqual(conn, m_conn)
        self.assertEqual(1, m_conn_handler.call_count)

    @mock.patch.object(netmiko, 'ConnectHandler')
    def test__get_connection_disconnects_on_caller_failure(
            self, m_conn_handler):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        m_conn = mock.MagicMock(netmiko.base_connection.BaseConnection)
        m_conn_handler.return_value = m_conn

        class FakeError(Exception):
            pass

        def get_connection():
            with switch._get_connection():
                raise FakeError()

        self.assertRaises(FakeError, get_connection)
        m_conn.disconnect.assert_called_once_with()
        self.assertTrue(switch._connection_pool.empty())

    @mock.patch.object(netmiko, 'ConnectHandler')
    def test__get_connection_skips_dead_connections(
            self, m_conn_handler):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        dead_conn = mock.MagicMock(netmiko.base_connection.BaseConnection)
        dead_conn.is_alive.return_value = False
        live_conn = mock.MagicMock(netmiko.base_connection.BaseConnection)
        m_conn_handler.side_effect = [dead_conn, live_conn]

        # First call creates dead_conn and returns it to pool
        with switch._get_connection() as conn:
            self.assertEqual(conn, dead_conn)

        # Second call finds dead_conn in pool, discards it, creates live_conn
        with switch._get_connection() as conn:
            self.assertEqual(conn, live_conn)

        self.assertEqual(2, m_conn_handler.call_count)
        dead_conn.disconnect.assert_called_once_with()

    def test__drain_cached_connections(self):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
            'ngs_max_connections': 2,
        })
        conn1 = mock.MagicMock(netmiko.base_connection.BaseConnection)
        conn2 = mock.MagicMock(netmiko.base_connection.BaseConnection)
        switch._connection_pool.put_nowait(conn1)
        switch._connection_pool.put_nowait(conn2)

        switch._drain_cached_connections()

        conn1.disconnect.assert_called_once_with()
        conn2.disconnect.assert_called_once_with()
        self.assertTrue(switch._connection_pool.empty())

    @mock.patch.object(netmiko_devices.NetmikoSwitch, '_get_connection')
    def test_send_commands_to_device_empty(self, gc_mock):
        connect_mock = mock.MagicMock()
        gc_mock.return_value.__enter__.return_value = connect_mock
        self.assertIsNone(self.switch.send_commands_to_device([]))
        self.assertFalse(connect_mock.send_config_set.called)
        self.assertFalse(connect_mock.send_command.called)

    @mock.patch.object(netmiko, 'ConnectHandler')
    def test_send_commands_to_device_reuses_cached_connection(
            self, m_conn_handler):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        connection = mock.MagicMock(netmiko.base_connection.BaseConnection)
        m_conn_handler.return_value = connection

        switch.send_commands_to_device(['cmd1'])
        switch.send_commands_to_device(['cmd2'])
        self.assertEqual(1, m_conn_handler.call_count)

    @mock.patch.object(netmiko, 'ConnectHandler')
    def test_send_commands_to_device_does_not_share_cached_connection(
            self, m_conn_handler):
        switch1 = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        switch2 = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        first_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        second_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        m_conn_handler.side_effect = [first_connection, second_connection]

        switch1.send_commands_to_device(['cmd1'])
        switch2.send_commands_to_device(['cmd1'])

        self.assertEqual(2, m_conn_handler.call_count)

    @mock.patch.object(netmiko, 'ConnectHandler')
    def test_send_commands_to_device_replaces_dead_cached_connection(
            self, m_conn_handler):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        first_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        second_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        first_connection.is_alive.return_value = False
        m_conn_handler.side_effect = [first_connection, second_connection]

        switch.send_commands_to_device(['cmd1'])
        switch.send_commands_to_device(['cmd2'])

        self.assertEqual(2, m_conn_handler.call_count)
        first_connection.disconnect.assert_called_once_with()
        second_connection.disconnect.assert_not_called()

    @mock.patch.object(netmiko, 'ConnectHandler')
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'send_config_set',
                       autospec=True)
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'save_configuration',
                       autospec=True)
    def test_send_commands_to_device_retries_cached_connection_failure(
            self, save_mock, send_mock, m_conn_handler):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        first_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        second_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        m_conn_handler.side_effect = [first_connection, second_connection]
        send_mock.side_effect = [Exception("stale shell"), "fake output"]

        output = switch.send_commands_to_device(['cmd1'])

        self.assertEqual("fake output", output)
        self.assertEqual(2, m_conn_handler.call_count)
        send_mock.assert_has_calls([
            mock.call(switch, first_connection, ['cmd1']),
            mock.call(switch, second_connection, ['cmd1'])
        ])
        first_connection.disconnect.assert_called_once_with()
        second_connection.disconnect.assert_not_called()
        save_mock.assert_called_once_with(switch, second_connection)

    @mock.patch.object(netmiko, 'ConnectHandler')
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'send_config_set',
                       autospec=True)
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'save_configuration',
                       autospec=True)
    def test_send_commands_to_device_second_failure_raises(
            self, save_mock, send_mock, m_conn_handler):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })
        first_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        second_connection = mock.MagicMock(
            netmiko.base_connection.BaseConnection)
        m_conn_handler.side_effect = [first_connection, second_connection]
        send_mock.side_effect = [Exception("stale shell"),
                                 Exception("stale shell again")]

        self.assertRaises(
            exc.GenericSwitchNetmikoConnectError,
            switch.send_commands_to_device,
            ['cmd1'])
        self.assertEqual(2, m_conn_handler.call_count)
        self.assertEqual(2, send_mock.call_count)
        first_connection.disconnect.assert_called_once_with()
        second_connection.disconnect.assert_called_once_with()
        save_mock.assert_not_called()

    @mock.patch.object(netmiko_devices.NetmikoSwitch, '_get_connection')
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'send_config_set')
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'save_configuration')
    def test_send_commands_to_device(self, save_mock, send_mock, gc_mock):
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection)
        gc_mock.return_value.__enter__.return_value = connect_mock
        send_mock.return_value = 'fake output'
        result = self.switch.send_commands_to_device(['spam ham aaaa'])
        send_mock.assert_called_once_with(connect_mock, ['spam ham aaaa'])
        self.assertEqual('fake output', result)
        save_mock.assert_called_once_with(connect_mock)

    @mock.patch.object(netmiko_devices.NetmikoSwitch, '_get_connection')
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'send_config_set')
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'save_configuration')
    def test_send_commands_to_device_without_save_config(self, save_mock,
                                                         send_mock, gc_mock):
        switch = self._make_switch_device(
            extra_cfg={'ngs_save_configuration': False})
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection)
        gc_mock.return_value.__enter__.return_value = connect_mock
        send_mock.return_value = 'fake output'
        result = switch.send_commands_to_device(['spam ham aaaa'])
        send_mock.assert_called_once_with(connect_mock, ['spam ham aaaa'])
        self.assertEqual('fake output', result)
        save_mock.assert_not_called()

    @mock.patch.object(netmiko_devices.NetmikoSwitch,
                       '_drain_cached_connections')
    @mock.patch.object(netmiko_devices.NetmikoSwitch,
                       'check_output',
                       side_effect=exc.GenericSwitchNetmikoConfigError())
    @mock.patch.object(netmiko_devices.NetmikoSwitch,
                       'send_commands_to_device',
                       return_value='fake output')
    def test_check_output_failure_invalidates_cached_connection(
            self, send_mock, check_mock, invalidate_mock):
        switch = self._make_switch_device({
            'ngs_ssh_reuse_connection': True,
        })

        self.assertRaises(
            exc.GenericSwitchNetmikoConfigError,
            switch.add_network,
            22,
            '0ae071f5-5be9-43e4-80ea-e41fefe85b21')
        send_mock.assert_called_once()
        check_mock.assert_called_once_with(
            'fake output', 'add network')
        invalidate_mock.assert_called_once_with()

    def test_send_config_set(self):
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection)
        connect_mock.send_config_set.return_value = 'fake output'
        result = self.switch.send_config_set(connect_mock, ['spam ham aaaa'])
        connect_mock.enable.assert_called_once_with()
        connect_mock.send_config_set.assert_called_once_with(
            config_commands=['spam ham aaaa'], cmd_verify=False)
        self.assertEqual('fake output', result)

    @mock.patch.object(netmiko_devices.NetmikoSwitch, '_get_connection')
    def test_send_commands_to_device_send_failure(self, gc_mock):
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection)
        gc_mock.return_value.__enter__.return_value = connect_mock

        class FakeError(Exception):
            pass
        connect_mock.send_config_set.side_effect = FakeError
        self.assertRaises(exc.GenericSwitchNetmikoConnectError,
                          self.switch.send_commands_to_device,
                          ['spam ham aaaa'])
        connect_mock.send_config_set.assert_called_once_with(
            config_commands=['spam ham aaaa'], cmd_verify=False)

    @mock.patch.object(netmiko_devices.NetmikoSwitch, '_get_connection')
    def test_send_commands_to_device_send_ngs_failure(self, gc_mock):
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection)
        gc_mock.return_value.__enter__.return_value = connect_mock

        class NGSFakeError(exc.GenericSwitchException):
            pass
        connect_mock.send_config_set.side_effect = NGSFakeError
        self.assertRaises(NGSFakeError, self.switch.send_commands_to_device,
                          ['spam ham aaaa'])
        connect_mock.send_config_set.assert_called_once_with(
            config_commands=['spam ham aaaa'], cmd_verify=False)

    @mock.patch.object(netmiko_devices.NetmikoSwitch, '_get_connection')
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'save_configuration')
    def test_send_commands_to_device_save_failure(self, save_mock, gc_mock):
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection)
        gc_mock.return_value.__enter__.return_value = connect_mock

        class FakeError(Exception):
            pass
        save_mock.side_effect = FakeError
        self.assertRaises(exc.GenericSwitchNetmikoConnectError,
                          self.switch.send_commands_to_device,
                          ['spam ham aaaa'])
        connect_mock.send_config_set.assert_called_once_with(
            config_commands=['spam ham aaaa'], cmd_verify=False)
        save_mock.assert_called_once_with(connect_mock)

    @mock.patch.object(netmiko_devices.NetmikoSwitch, '_get_connection')
    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'save_configuration')
    def test_send_commands_to_device_save_ngs_failure(self, save_mock,
                                                      gc_mock):
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection)
        gc_mock.return_value.__enter__.return_value = connect_mock

        class NGSFakeError(exc.GenericSwitchException):
            pass
        save_mock.side_effect = NGSFakeError
        self.assertRaises(NGSFakeError, self.switch.send_commands_to_device,
                          ['spam ham aaaa'])
        connect_mock.send_config_set.assert_called_once_with(
            config_commands=['spam ham aaaa'], cmd_verify=False)
        save_mock.assert_called_once_with(connect_mock)

    def test_save_configuration(self):
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection,
                                      autospec=True)
        self.switch.save_configuration(connect_mock)
        connect_mock.save_config.assert_called_once_with()

    @mock.patch.object(netmiko_devices.NetmikoSwitch, 'SAVE_CONFIGURATION',
                       ('save', 'y'))
    def test_save_configuration_with_NotImplementedError(self):
        connect_mock = mock.MagicMock(netmiko.base_connection.BaseConnection,
                                      autospec=True)

        def fake_save_config():
            raise NotImplementedError
        connect_mock.save_config = fake_save_config
        self.switch.save_configuration(connect_mock)
        connect_mock.send_command.assert_has_calls([mock.call('save'),
                                                    mock.call('y')])

    @mock.patch.object(utils, 'get_hostname', autospec=True)
    @mock.patch.object(netmiko_devices.ngs_lock, 'PoolLock', autospec=True)
    @mock.patch.object(netmiko_devices.netmiko, 'ConnectHandler')
    @mock.patch.object(coordination, 'get_coordinator', autospec=True)
    def test_switch_send_commands_with_coordinator(self, get_coord_mock,
                                                   nm_mock, lock_mock,
                                                   mock_hostname):
        self.cfg.config(acquire_timeout=120, backend_url='mysql://localhost',
                        group='ngs_coordination')
        coord = mock.Mock()
        get_coord_mock.return_value = coord
        mock_hostname.return_value = 'viking'
        switch = self._make_switch_device(
            extra_cfg={'ngs_max_connections': 2})
        self.assertEqual(coord, switch.locker)
        get_coord_mock.assert_called_once_with('mysql://localhost',
                                               'ngs-viking'.encode('ascii'))

        connect_mock = mock.MagicMock(SAVE_CONFIGURATION=None)
        connect_mock.__enter__.return_value = connect_mock
        nm_mock.return_value = connect_mock
        lock_mock.return_value.__enter__.return_value = lock_mock
        switch.send_commands_to_device(['spam ham'])

        lock_mock.assert_called_once_with(coord, locks_pool_size=2,
                                          locks_prefix='host',
                                          timeout=120)
        lock_mock.return_value.__exit__.assert_called_once()
        lock_mock.return_value.__enter__.assert_called_once()
        mock_hostname.assert_called_once()

    def test_check_output(self):
        self.switch.check_output('fake output', 'fake op')

    def test_check_output_error(self):
        self.switch.ERROR_MSG_PATTERNS = (re.compile('fake error message'),)
        output = """
fake switch command
fake error message
"""
        msg = ("Found invalid configuration in device response. Operation: "
               "fake op. Output: %s" % output)
        self.assertRaisesRegex(exc.GenericSwitchNetmikoConfigError, msg,
                               self.switch.check_output, output, 'fake op')
