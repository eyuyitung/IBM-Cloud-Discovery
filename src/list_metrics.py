import SoftLayer
import config


client = SoftLayer.create_client_from_env(config.USERNAME, config.API_KEY)
mgr = SoftLayer.HardwareManager(client)
object_mask = "mask[hostname,monitoringRobot[robotStatus]]"
result = mgr.list_hardware(mask=object_mask)

print(result)