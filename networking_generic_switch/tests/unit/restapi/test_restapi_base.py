from unittest import mock

import fixtures
from oslo_config import fixture as config_fixture

from networking_generic_switch import exceptions as exc
from networking_generic_switch.devices import restapi_devices, utils


class RestAPISwitchTestBase(fixtures.TestWithFixtures):
    def setUp(self) -> None:
        super().setUp()
        self.cfg = self.useFixture(config_fixture.Config())
        self.switch = self._make_switch_device()

    def _make_switch_device(self, extra_cfg={}):
        device_cfg = {"ip": "host"}
        device_cfg.update(extra_cfg)
        return restapi_devices.RestAPISwitch(device_cfg)


class TestRestAPISwitch(RestAPISwitchTestBase):
    def test_add_network(self):
        self.switch.add_network(22, "0ae071f5-5be9-43e4-80ea-e41fefe85b21")
        # m_sctd.assert_called_with([])
        # m_check.assert_called_once_with('fake output', 'add network')

    def test_add_network_with_no_manage_vlans(self):
        switch = self._make_switch_device({"ngs_manage_vlans": False})
        switch.add_network(22, "0ae071f5-5be9-43e4-80ea-e41fefe85b21")
        # self.assertFalse(m_sctd.called)
        # m_check.assert_called_once_with("", "add network")

    def test_del_network(self):
        self.switch.del_network(22, "0ae071f5-5be9-43e4-80ea-e41fefe85b21")
        # m_sctd.assert_called_with([])
        # m_check.assert_called_once_with("fake output", "delete network")

    def test_del_network_with_no_manage_vlans(self):
        switch = self._make_switch_device({"ngs_manage_vlans": False})
        switch.del_network(22, "0ae071f5-5be9-43e4-80ea-e41fefe85b21")
        # self.assertFalse(m_sctd.called)
        # m_check.assert_called_once_with('', 'delete network')

    def test_plug_port_to_network(self):
        self.switch.plug_port_to_network(2222, 22)
        # m_sctd.assert_called_with([])
        # m_check.assert_called_once_with("fake output", "plug port")

    def test_delete_port(self):
        self.switch.delete_port(2222, 22)
        # m_sctd.assert_called_with([])
        # m_check.assert_called_once_with("fake output", "unplug port")
