import SoftLayer
import config
import json
from datetime import *
import time
start = time.perf_counter()

client = SoftLayer.create_client_from_env(config.USERNAME, config.API_KEY)
accountService = client['SoftLayer_Account']

sampleSizeHours = 24
metricEndDate = (datetime.now(timezone.utc))
metricStartDate = metricEndDate + timedelta(hours=-sampleSizeHours)



def print_json(file):
    print(json.dumps(file, sort_keys=True, indent=2, separators=(',', ': ')))


def main():
    systems = {}
    
    for virtualGuestConfig in accountService.getVirtualGuests():
        virtual_id = virtualGuestConfig['id']
        # print_json(virtualGuestConfig)
        virtualGuestConfig['operatingSystem'] = client['SoftLayer_Virtual_Guest'].getOperatingSystem(id=virtual_id)
        virtualGuestConfig['location'] = client['SoftLayer_Virtual_Guest'].getRegionalGroup(id=virtual_id)
        virtualGuestConfig['location']["datacenter"] = client['SoftLayer_Virtual_Guest'].getDatacenter(id=virtual_id)
        systems[virtual_id] = [virtualGuestConfig]
        # instance metrics
        cpuMetric = client['SoftLayer_Virtual_Guest'].getCpuMetricDataByDate(metricStartDate, metricEndDate, id=virtual_id)
        cpuMetric = [{'Timestamps': ['2018-08-12:09:15:00Z'], 'Data': ['52.001547']}]  # placeholder values
        systems[virtual_id].append(cpuMetric)

    print_json(systems)








'''
object_mask = "mask[hostname,monitoringRobot[robotStatus]]"
result = mgr.list_hardware(mask=object_mask)

print(result)
    
objectMask = "mask[userCount]"    
'''

if __name__ == '__main__':
    main()

end = time.perf_counter()
print(str(end - start))