import atexit

from oslo_config import cfg
from oslo_log import log as logging

from networking_generic_switch import devices
from tooz import coordination
from networking_generic_switch.devices import utils as device_utils

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class RestAPISwitch(devices.GenericSwitchDevice):
    def __init__(self, device_cfg, *args, **kwargs):
        super(RestAPISwitch, self).__init__(device_cfg, *args, **kwargs)

        device_type = self.config.get("device_type", "")
        device_type = device_type.partition("restapi_")[2]
        self.config["device_type"] = device_type

        self.lock_kwargs = {
            'locks_pool_size': int(self.ngs_config['ngs_max_connections']),
            'locks_prefix': self.config.get(
                'host', '') or self.config.get('ip', ''),
            'timeout': CONF.ngs_coordination.acquire_timeout}

        self.locker = None
        if CONF.ngs_coordination.backend_url:
            self.locker = coordination.get_coordinator(
                CONF.ngs_coordination.backend_url,
                ('ngs-' + device_utils.get_hostname()).encode('ascii'))
            self.locker.start()
            atexit.register(self.locker.stop)
        else:
            LOG.warning(
                "Switch %s: [ngs_coordination] backend_url is not "
                "configured. The ngs_max_connections is ignored.",
                self.lock_kwargs['locks_prefix'])

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
