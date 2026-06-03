from oslo_config import cfg
from oslo_log import log as logging

from networking_generic_switch import devices

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class RestAPISwitch(devices.GenericSwitchDevice):
    def __init__(self, device_cfg, *args, **kwargs):
        super(RestAPISwitch, self).__init__(device_cfg, *args, **kwargs)

        device_type = self.config.get("device_type", "")
        device_type = device_type.partition("restapi_")[2]
        self.config["device_type"] = device_type

    def add_network(self, segmentation_id, network_id):
        if not self._do_vlan_management():
            LOG.info(f"Skipping add network for {segmentation_id}")

    def del_network(self, segmentation_id, network_id):
        if not self._do_vlan_management():
            LOG.info(f"Skipping delete network for {segmentation_id}")

    def plug_port_to_network(self, port_id, segmentation_id):
        pass

    def delete_port(self, port_id, segmentation_id):
        pass
