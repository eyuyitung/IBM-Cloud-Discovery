import SoftLayer

USERNAME = 'snewton@densify.com'
API_KEY = ''

client = SoftLayer.create_client_from_env(USERNAME,API_KEY)
mgr = SoftLayer.HardwareManager(client)
object_mask = "mask[hostname,monitoringRobot[robotStatus]]"
result = mgr.list_hardware(mask=object_mask)

print(result)