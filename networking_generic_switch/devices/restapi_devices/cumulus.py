import sys
import ssl

# Save the original property
#_original_minimum_version = ssl.SSLContext.minimum_version

# Create a fixed property that doesn't recurse
#def _fixed_minimum_version_getter(self):
    #return self._minimum_version if hasattr(self, '_minimum_version') else ssl.TLSVersion.TLSv1_2

#def _fixed_minimum_version_setter(self, value):
    #self._minimum_version = value

#ssl.SSLContext.minimum_version = property(_fixed_minimum_version_getter, _fixed_minimum_version_setter)

import json
import time
import requests
from oslo_config import cfg
from oslo_log import log as logging
from requests.auth import HTTPBasicAuth
import urllib3

from networking_generic_switch.devices import restapi_devices

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

        self.nvue_end_point = "https://10.23.252.7:8765/nvue_v1"
        self.auth = HTTPBasicAuth(
            username="foo",
            password="bar",
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
                #print(response)
                return True
            retries -= 1
            time.sleep(poll_applied)

        return False

    def send_commands_to_device(self, path, payload):
        # TODO: verify response, add loggging
        revision = self._create_revision()
        print("Created revision " + str(revision) + ".")

        # TODO: verify response, add loggging
        patched = self._submit_patch(revision, path, payload)

        # TODO: verify response, add loggging
        applied = self._apply_patch(revision)

        # TODO: verify response, add loggging
        result = self._wait_for_applied(revision)

        if not result:
            print ("Failed to apply patch: rev = " + str(revision) + ", path = " + str(path) + ", payload = " + str(payload)) 
        else:
            print("Successfully applied patch: rev = " + str(revision) + ", path = " + str(path) + ", payload = " + str(payload))

    def add_network(self, segmentation_id, network_id):
        print("Adding network: " + str(segmentation_id))

        # TODO -- Add bridge and interface variables either passed in or collected from network_id lookup
        bridge_name = "thunderbr"
        
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
        
    def del_network(self, segmentation_id, network_id):
        print("Deleting network: " + str(segmentation_id))

        bridge_name = "thunderbr"
        
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
        print("plug_port_to_network test on " + str(port_id) + " with VLAN " + str(segmentation_id))

        # TODO
        bridge_name = "thunderbr"
       

        #print("nv set interface " + str(port_id) + " link state up")
        #"nv set interface {port_id} link state up"
        #"nv set interface {port_id} bridge domain {bridge_name} vlan {segmentation_id}"
        #"nv set interface {port_id} bridge domain {bridge_name} untagged {segmentation_id}""
        path = self.nvue_end_point + "/interface"
        payload = {
                            str(port_id): {
                                    "link": {
                                        "state": {
                                            "up": {}
                                        }
                                    },
                                    "bridge": {
                                        "domain": {
                                            bridge_name: {
                                                "untagged": segmentation_id,
                                                "vlan": {
                                                    str(segmentation_id): {}
                                                }
                                            }
                                        }
                                    }
                            }
                    }
        self.send_commands_to_device(path=path, payload=payload)

        """
        print("nv unset interface " + str(port_id) + "bridge domain " + str(bridge_name) + " access")
        #"nv unset interface {port_id} bridge domain {bridge_name} access"
        payload = {
                "unset": {
                        "interface": {
                                str(port_id): {
                                        "bridge": {
                                        "domain": {
                                                bridge_name: {
                                                        "access": None
                                                }
                                        }
                                        }
                                }
                        }
                }
                }
        self.send_commands_to_device(path=path, payload=payload)

        print("nv unset interface " + str(port_id) + " bridge domain " + str(bridge_name) + " untagged") 
        #"nv unset interface {port_id} bridge domain {bridge_name} untagged"
        payload = {
            "unset": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "untagged": None
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        print("nv set interface " + str(port_id) + " bridge domain " + str(bridge_name) + " vlan " + str(segmentation_id))
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

        print("nv set interface " + str(port_id) + " bridge domain " + str(bridge_name) + " untagged " + str(segmentation_id))
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
    """
    def delete_port(self, port_id, segmentation_id):
        print("Deleteing VLAN " + str(segmentation_id) + " from port " + str(port_id)) 
        # TODO
        bridge_name = "thunderbr"
        
        #print("nv unset interface " + str(port_id) + " bridge domain " + str(bridge_name) + " access")
        #"nv set interface {port_id} bridge domain {bridge_name} vlan 1"
        #"nv set interface {port_id} bridge domain {bridge_name} untagged 1"
        path = self.nvue_end_point + "/interface"
        payload = {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "untagged": 1,
                                    "vlan": {
                                        "1": {}
                                    }
                                }
                            }
                        }
                    }
                }
        self.send_commands_to_device(path=path, payload=payload)
"""
        print("nv unset interface " + str(port_id) + " bridge domain " + str(bridge_name) + " untagged")
        #"nv unset interface {port_id} bridge domain {bridge_name} untagged"
        payload = {
            "unset": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "untagged": None
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        print("nv unset interface " + str(port_id) + " bridge domain " + str(bridge_name) + " vlan")
        #"nv unset interface {port_id} bridge domain {bridge_name} vlan"
        payload = {
            "unset": {
                "interface": {
                    str(port_id): {
                        "bridge": {
                            "domain": {
                                bridge_name: {
                                    "vlan": None
                                }
                            }
                        }
                    }
                }
            }
        }
        self.send_commands_to_device(path=path, payload=payload)

        print("nv set interface " + str(port_id) + " bridge domain " + str(bridge_name) + " vlan 1")
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

        print("nv set interface " + str(port_id) + " bridge domain " + str(bridge_name) + " untagged 1")
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
    """