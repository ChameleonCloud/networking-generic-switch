import requests
from oslo_config import cfg
from oslo_log import log as logging
from requests.auth import HTTPBasicAuth

from networking_generic_switch.devices import restapi_devices

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class CumulusNVUE(restapi_devices.RestAPISwitch):
    """Cumulus Switch NVUE Interface

    Cumulus NVUE assumes the following flow for applying changes:
    1. create new revision ID via POST
    2. submit change via PATCH, linked to revision ID
    3. apply change via PATCH to revision
    4. confirm success by sending GET separately to revision and changed object
    """

    mime_header = {"Content-Type": "application/json"}

    def __init__(self, device_cfg, *args, **kwargs):
        super(CumulusNVUE, self).__init__(device_cfg, *args, **kwargs)
        # TODO get endpoint and auth from config instead of hardcoding...

        self.nvue_end_point = "foo"
        self.auth = HTTPBasicAuth(
            username="bar",
            password="baz",
        )

    def _create_revision(self):
        r = requests.post(
            url=self.nvue_end_point + "/revision",
            auth=self.auth,
            verify=False,
        )
        response = r.json()
        changeset = response.popitem()[0]
        return changeset

    def _submit_patch(self, revision, path, payload):
        query_string = {"rev": revision}
        r = requests.patch(
            url=self.nvue_end_point + path,
            auth=self.auth,
            verify=False,
            data=payload,
            params=query_string,
            headers=self.mime_header,
        )
        return r

    def _apply_patch(self, revision):
        apply_payload = {"state": "apply"}
        url = self.nvue_end_point + "/revision/" + revision
        r = requests.patch(
            url=url,
            auth=self.auth,
            verify=False,
            data=apply_payload,
            headers=self.mime_header,
        )
        return r

    def _wait_for_applied(self, revision):
        # TODO .....
        pass

    def send_commands_to_device(self, path, payload):
        # TODO: verify response, add loggging
        revision = self._create_revision()

        # TODO: verify response, add loggging
        patched = self._submit_patch(revision, path, payload)

        # TODO: verify response, add loggging
        applied = self._apply_patch(revision)

        # TODO: verify response, add loggging
        result = self._wait_for_applied(revision)

    def add_network(self, segmentation_id, network_id):
        # TODO
        path = ""
        payload = ""
        self.send_commands_to_device(path=path, payload=payload)

    def del_network(self, segmentation_id, network_id):
        # TODO
        path = ""
        payload = ""
        self.send_commands_to_device(path=path, payload=payload)

    def plug_port_to_network(self, port_id, segmentation_id):
        # TODO
        path = ""
        payload = ""
        self.send_commands_to_device(path=path, payload=payload)

    def delete_port(self, port_id, segmentation_id):
        # TODO
        path = ""
        payload = ""
        self.send_commands_to_device(path=path, payload=payload)
