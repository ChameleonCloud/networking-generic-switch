import sys
import ssl

#save the original property
_original_minimum_version = ssl.SSLContext.minimum_version

#create a fixed property that shouldn't recurse
def _fixed_minimum_version_getter(self):
    return self._minimum_version if hasattr(self, '_minimum_version') else ssl.TLSVersion.TLSv1_2

def _fixed_minimum_version_setter(self, value):
    self._minimum_version = value

ssl.SSLContext.minimum_version = property(_fixed_minimum_version_getter, _fixed_minimum_version_setter)

import json
import time
import requests
from oslo_config import cfg
from oslo_log import log as logging
from requests.auth import HTTPBasicAuth
import urllib3

from networking_generic_switch.devices import restapi_devices

#disable ssl warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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
        apply_payload = {"state": "apply", "auto-prompt": {"ays": "ays_yes"}}
        url = self.nvue_end_point + "/revision/" + requests.utils.quote(revision,safe="")
        r = requests.patch(
            url=url,
            auth=self.auth,
            verify=False,
            data=json.dumps(apply_payload),
            headers=self.mime_header,
        )
        return r

    def _wait_for_applied(self, revision):
        # TODO .....
        retries = 20
        poll_applied = 2
        url=self.nvue_end_point + "/revision/" + requests.utils.quote(revision, safe="")

        while retries > 0:
            r  = requests.get(
                url=url,
                auth=self.auth,
                verify=False
            )
            response = r.json()
            if response["state"] == "applied":
                return True
            retries -= 1
            time.sleep(poll_applied)

        return False

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
        # TODO -- Add bridge and interface variables either passed in or collected from network_id lookup
        bridge_name = "br_default"
        
        #"nv set bridge domain {bridge_name} vlan {segmentation_id}
        path = self.nvue_end_point

        payload = {
            "set": {
                "bridge": {
                    "domain": {
                        bridge_name: {
                            "vlan": {
                                str(segmentation_id): {}
                            }
                        }
                    }
                }
            }
        }

        self.send_commands_to_device(path=path, payload=payload)
        
    def del_network(self, segmentation_id):
        bridge_name = "br_default"
        
        #"nv unset bridge domain {bridge_name} vlan {segmentation_id}
        path = self.nvue_end_point
        payload = {
            "unset": {
                "bridge": {
                    "domain": {
                        bridge_name: {
                            "vlan": {
                                str(segmentation_id): {}
                            }
                        }
                    }
                }
            }
        }

        self.send_commands_to_device(path=path, payload=payload)   
    def plug_port_to_network(self, port_id, segmentation_id):
        # TODO
        bridge_name = "br_default"
        
        #"nv set interface {port_id} link state up"
        path = self.nvue_end_point
        payload = {
                "set": {
                        "interface": {
                                str(port_id): {
                                        "link": {
                                        "state": {
                                                "up": {}
                                        }
                                        }
                                }
                        }
                }
        }
        self.send_commands_to_device(path=path, payload=payload)


        #"nv unset interface {port_id} bridge domain {bridge_name} access"
        payload = {
                "unset": {
                        "interface": {
                                str(port_id): {
                                        "bridge": {
                                        "domain": {
                                                bridge_name: {
                                                        "access": null
                                                }
                                        }
                                        }
                                }
                        }
                }
                }
        self.send_commands_to_device(path=path, payload=payload)

        #"nv unset interface {port_id} bridge domain {bridge_name} untagged"
        payload = {
            "unset": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "untagged": null
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        #"nv set interface {port_id} bridge domain {bridge_name} vlan {segmentation_id}"
        payload = {
            "set": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "vlan": {
                                        str(segmentation_id): {}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        #"nv set interface {port_id} bridge domain {bridge_name} untagged {segmentation_id}
        payload = {
            "set": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "untagged": segmentation_id
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)
    def delete_port(self, port_id, segmentation_id):
        # TODO
        bridge_name = "br_default"
        
        #"nv unset interface {port_id} bridge domain {bridge_name} access"
        path = self.nvue_end_point
        payload = {
            "unset": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "access": null
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        #"nv unset interface {port_id} bridge domain {bridge_name} untagged"
        payload = {
            "unset": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "untagged": null
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        #"nv unset interface {port_id} bridge domain {bridge_name} vlan"
        payload = {
            "unset": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "vlan": null
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        #"nv set interface {port_id} bridge domain {bridge_name} vlan 1"
        payload = {
            "set": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "vlan": {
                                        "1": {}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        #"nv set interface {port_id} bridge domain {bridge_name} untagged 1"
        payload = {
            "set": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "untagged": 1
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)