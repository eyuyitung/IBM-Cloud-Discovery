import SoftLayer
import config
from datetime import *
import time
from pandas import *
import json

####
start = time.perf_counter()
print("start")
####

client = SoftLayer.create_client_from_env(config.USERNAME, config.API_KEY)
accountService = client['SoftLayer_Account']
sampleSizeHours = 24 # max = 85 without reducing sample rate
now = (datetime.now(timezone(-timedelta(hours=5))))
metricEndDate = datetime.strftime(now, "%Y-%m-%dT%H:%M%z")
metricStartDate = datetime.strftime(now - timedelta(hours=sampleSizeHours), "%Y-%m-%dT%H:%M%z")




def main():
    get_config()


def get_config():
    object_mask = "mask[id, maxMemory, maxCpu, datacenter.name, regionalGroup.name, " \
                  "operatingSystem.softwareLicense.softwareDescription.name, hostname, powerState]"
    masked_call = accountService.getVirtualGuests(mask=object_mask)
    sys_conf = {}
    for account in masked_call:
        account['datacenter'] = account['datacenter']['name']
        account['operatingSystem'] = account['operatingSystem']['softwareLicense']['softwareDescription']['name']
        account['regionalGroup'] = account['regionalGroup']['name']
        account['maxMemory'] = int(account['maxMemory']/1024)
        account['powerState'] = account['powerState']['name']
        print_json(account)
        fields = account.keys()
        sys_conf[account['id']] = list(account.values())

    df = DataFrame.from_dict(sys_conf, orient='index', columns=fields)
    df.to_csv("conf.csv")
    get_metrics(df.index)


def get_metrics(virtual_ids):
    metric_dict = {}
    metrics = ["cpu_utilization", "memory_usage", "network_in", "network_out"]
    for virtual_id in virtual_ids:
        inst_metric_names = ('Cpu', 'Memory', 'Bandwidth')
        inst_dict = {}
        for metric_name in inst_metric_names:
            #  Virtual_guest default metrics
            if metric_name != 'Bandwidth':
                response = client.call('Virtual_Guest', 'get' + metric_name + 'MetricDataByDate',
                                                          metricStartDate, metricEndDate, id=virtual_id)
            else:
                response = client.call('Virtual_Guest', 'get' + metric_name + 'DataByDate',
                                                          metricStartDate, metricEndDate, id=virtual_id)

            inst_dict[response[0]['type']] = {}
            for data_point in response: # populating inst dict with type : {time : value}
                if data_point['type'] not in inst_dict.keys():  # add datatype if missing (2 type return from 1 call)
                    inst_dict[data_point['type']] = {}
                inst_dict[data_point['type']][data_point['dateTime']] = data_point['counter']

        for key, value in inst_dict.items():
            inst_dict[key] = Series(data=list(value.values()), index=value.keys())
        inst_ts = concat(inst_dict.values(), axis=1, keys=metrics)
        metric_dict[virtual_id] = inst_ts

    df = concat(metric_dict.values(), keys=virtual_ids)
    df.to_csv("metric.csv")
    end = time.perf_counter()
    print(str(end - start))


def print_json(file):  # json output shortcut
    print(json.dumps(file, sort_keys=True, indent=2, separators=(',', ': ')))



'''
object_mask = "mask[hostname,monitoringRobot[robotStatus]]"
result = mgr.list_hardware(mask=object_mask)

print(result)
    
objectMask = "mask[userCount]"    


        
        
        memory_metric = client.call('Virtual_Guest', 'getMemoryMetricDataByDate', metricStartDate, metricEndDate, id=virtual_id)
        bandwidth_metric = client.call('Virtual_Guest', 'getBandwidthDataByDate', metricStartDate, metricEndDate, id=virtual_id)

        
        sys_metrics[virtual_id] = [cpu_metric]
        sys_metrics[virtual_id].append(memory_metric)
        sys_metrics[virtual_id].append(bandwidth_metric)


     type_ts = {response[0]['type']: {}} #type : data time-series
            for item in response:  # handling multiple metrics returned in call
                if item['type'] not in type_ts.keys():
                    type_ts[item['type']] = {}
                type_ts[item['type']] [item['dateTime']] = item['counter']  # assigning dataseries to type

            for key, value in type_ts.items():
                tmp[key] = Series(list(value.values()), index=value.keys()) # convert dict to ts


'''

if __name__ == '__main__':
    main()
