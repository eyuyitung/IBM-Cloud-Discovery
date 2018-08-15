'''
    This is a prototype for IBM Cloud metric collection.

    Created on: 8/2/2018
    Last Update on: 8/13/2018

    Authors:
        Eric Yuyitung
        Stephen Newton
'''

#  Import statements
import SoftLayer
from src import config
from datetime import *
import time
from pandas import *
import json

####
start = time.perf_counter()
print("Start:", '0.00')
####

# Declaring the client using login details
client = SoftLayer.create_client_from_env(config.USERNAME, config.API_KEY)

# SoftLayer API services
accountService = client['SoftLayer_Account']
agentService = client['SoftLayer_Monitoring_Agent']

# Date and time ranges/functions
sampleSizeHours = 24
now = (datetime.now(timezone(-timedelta(hours=5))))
metricEndDate = datetime.strftime(now, "%Y-%m-%dT%H:%M%z")
metricStartDate = datetime.strftime(now - timedelta(hours=sampleSizeHours), "%Y-%m-%dT%H:%M%z")

# The main
def main():
    get_config()

# Gets the configuration values for a VSI (CPU, RAM, OS, Name, DataCenter, PowerState)
def get_config():

    # Creates an array for the system config
    sys_conf = {}

    # The object mask of the query (to limit and filter data returned)
    object_mask = "mask[id, maxMemory, maxCpu, datacenter.name, regionalGroup.name, " \
                  "operatingSystem.softwareLicense.softwareDescription.name, hostname, powerState, monitoringAgents]"

    # Queries the SoftLayer API with mask applied
    masked_call = accountService.getVirtualGuests(mask=object_mask)

    # For each account in the returned from the masked_call, flatten dictionary to desired information
    for account in masked_call:
        account['datacenter'] = account['datacenter']['name']
        account['operatingSystem'] = account['operatingSystem']['softwareLicense']['softwareDescription']['name']
        account['regionalGroup'] = account['regionalGroup']['name']
        account['maxMemory'] = int(account['maxMemory']/1024)
        account['powerState'] = account['powerState']['name']

        # For each drive on account, print id and account as seperate tagged columns
        drive_tag = 1
        for disk in account['blockDevices']:
            if 'diskImage' in disk.keys():  # assuming only relevant drives are disk drives
                d = disk['diskImage']
                if d['capacity'] >= 25 and d['units'] == 'GB':
                    account['drive_' + str(drive_tag) + '_id'] = disk['id']
                    account['drive_' + str(drive_tag) + '_capacity'] = (str(d['capacity']) + d['units'])
                    drive_tag += 1
        del account['blockDevices']  # drop superfluous column

        # If no monitoring agent is installed then nothing is printed
        if len(account['monitoringAgents']) > 0:
            account['monitoringAgents'] = account['monitoringAgents'][0]['id']
        else:
            account['monitoringAgents'] = 'N/A'

        # Stores the fields using the account keys and then sorts them by their IDs
        fields = account.keys()
        sys_conf[account['id']] = list(account.values())

    # Creates a data frame and prints it out to CSV file
    df = DataFrame.from_dict(sys_conf, orient='index', columns=fields)
    df = df.drop('id', axis=1)
    df.index.name = 'id'
    df.to_csv("conf.csv")

    # Calls the get_metrics method (uses the data frame from above)
    get_metrics(df.index)


# Gets the metrics for each VSI using info from the data frame from above
def get_metrics(virtual_ids):

    metric_dict = {}
    metrics = ["cpu_utilization", "memory_usage", "disk_usage", "network_in", "network_out"]
    inst_metric_names = ('Cpu', 'Memory', 'Disk', 'Bandwidth')

    # Loops through each VSI using a VSI ID grabbed from the account
    for virtual_id in virtual_ids:

        # Creates an instance dictionary each time a new VSI is found
        inst_dict = {}

        # Loops through each available metric for the current VSI
        for metric_name in inst_metric_names:

            # Picks the correct metric to query and stores it
            if metric_name == 'Cpu' or metric_name == 'Memory':
                response = client.call('Virtual_Guest', 'get' + metric_name + 'MetricDataByDate',
                                                          metricStartDate, metricEndDate, id=virtual_id)
            # Does not work as of 8/13/2018 -SHN
            elif metric_name == 'Disk':
                response = accountService.getDiskUsageMetricDataByDate(metricStartDate, metricEndDate, id=virtual_id)
                #response = accountService.getDiskUsageMetricDataFromMetricTrackingObjectSystemByDate(metricStartDate, metricEndDate, id=virtual_id)
                #  ^^ throws SoftLayer.exceptions.SoftLayerAPIError: SoftLayerAPIError(SoftLayer_Exception): $metrics collection must contain data.
            else:
                response = client.call('Virtual_Guest', 'get' + metric_name + 'DataByDate',
                                                          metricStartDate, metricEndDate, id=virtual_id)

            print(response)
            # If a usage value was collected from the API then continue
            if len(response) != 0:
                inst_dict[response[0]['type']] = {}

                for data_point in response: # populating inst dict with type : {time : value}
                    if data_point['type'] not in inst_dict.keys():  # add datatype if missing (2 type return from 1 call)
                        inst_dict[data_point['type']] = {}

                    inst_dict[data_point['type']][data_point['dateTime']] = data_point['counter']

            else:  # if no value returned from api
                inst_dict['n/a'] = {'n/a': None}

        # Stores values under the current metric
        for key, value in inst_dict.items():
            inst_dict[key] = Series(data=list(value.values()), index=value.keys())
        inst_ts = concat(inst_dict.values(), axis=1, keys=metrics, sort=True)
        metric_dict[virtual_id] = inst_ts

    # Creates a data frame and prints to CSV file
    df = concat(metric_dict.values(), keys=virtual_ids, sort=True)
    df.to_csv("metric.csv")

    # time taken to run program
    end = time.perf_counter()
    print("End:" , str(end - start))

# json output shortcut
def print_json(file):
    print(json.dumps(file, sort_keys=True, indent=2, separators=(',', ': ')))


# ensure program is running as a main process
if __name__ == '__main__':
    main()
