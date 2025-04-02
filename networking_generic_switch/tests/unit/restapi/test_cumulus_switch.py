from unittest import mock

from networking_generic_switch import exceptions as exc
from networking_generic_switch.devices.restapi_devices import cumulus
from networking_generic_switch.tests.unit.restapi.test_restapi_base import (
    RestAPISwitchTestBase,
)


class TestRestAPICumulus(RestAPISwitchTestBase):
    def _make_switch_device(self, extra_cfg={}):
        device_cfg = {"ip": "host"}
        device_cfg.update(extra_cfg)
        return cumulus.CumulusNVUE(device_cfg)

    def test_add_network(self):
        self.switch.add_network(22, "0ae071f5-5be9-43e4-80ea-e41fefe85b21")

    def test_add_network_with_no_manage_vlans(self):
        switch = self._make_switch_device({"ngs_manage_vlans": False})
        switch.add_network(22, "0ae071f5-5be9-43e4-80ea-e41fefe85b21")

    def test_del_network(self):
        self.switch.del_network(22, "0ae071f5-5be9-43e4-80ea-e41fefe85b21")

    def test_del_network_with_no_manage_vlans(self):
        switch = self._make_switch_device({"ngs_manage_vlans": False})
        switch.del_network(22, "0ae071f5-5be9-43e4-80ea-e41fefe85b21")

    def test_plug_port_to_network(self):
        self.switch.plug_port_to_network(2222, 22)

    def test_delete_port(self):
        self.switch.delete_port(2222, 22)
