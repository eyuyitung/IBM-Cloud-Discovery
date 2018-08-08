import SoftLayer
import config
import json
from datetime import *
import time


####
start = time.perf_counter()
print("start")
####

client = SoftLayer.create_client_from_env(config.USERNAME, config.API_KEY)
accountService = client['SoftLayer_Account']
sampleSizeHours = 24
now = (datetime.now(timezone(-timedelta(hours=5))))
metricEndDate = datetime.strftime(now, "%Y-%m-%dT%H:%M%z")
metricStartDate = datetime.strftime(now - timedelta(hours=sampleSizeHours), "%Y-%m-%dT%H:%M%z")
sys_conf = {}
sys_metrics = {}


def print_json(file):
    print(json.dumps(file, sort_keys=True, indent=2, separators=(',', ': ')))


def main():
    get_config()


def get_config():
    object_mask = "mask[id, maxMemory, maxCpu, datacenter.name, regionalGroup.name, " \
                  "operatingSystem.softwareLicense.softwareDescription.name]"
    masked_call = accountService.getVirtualGuests(mask=object_mask)
    for account in masked_call:
        sys_conf[account['id']] = [account]
    get_metrics(sys_conf.keys())


def get_metrics(virtual_ids):
    for virtual_id in virtual_ids:
        cpu_metric = client.call('Virtual_Guest', 'getCpuMetricDataByDate', metricStartDate, metricEndDate, id=virtual_id)
        ram_metric = client.call('Virtual_Guest', 'getMemoryMetricDataByDate', metricStartDate, metricEndDate, id=virtual_id)
        net_metric = client.call('Virtual_Guest', 'getBandwidthDataByDate', metricStartDate, metricEndDate, id=virtual_id)
        sys_metrics[virtual_id] = [cpu_metric]
        sys_metrics[virtual_id].append(ram_metric)
        sys_metrics[virtual_id].append(net_metric)

    print_json(sys_conf)
    print_json(sys_metrics)

    end = time.perf_counter()
    print(str(end - start))




'''
object_mask = "mask[hostname,monitoringRobot[robotStatus]]"
result = mgr.list_hardware(mask=object_mask)

print(result)
    
objectMask = "mask[userCount]"    
'''

if __name__ == '__main__':
    main()
