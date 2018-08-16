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

sampleSizeHours = 24  # max = 85 without reducing sample rate
now = (datetime.now(timezone(-timedelta(hours=5))))
metricEndDate = datetime.strftime(now, "%Y-%m-%dT%H:%M%z")
metricStartDate = datetime.strftime(now - timedelta(hours=sampleSizeHours), "%Y-%m-%dT%H:%M%z")


# Agent config parameters

agentName = 'Cpu, Disk, and Memory Monitoring Agent'
reports = {
    # Create graphs for Disk Usage (in MB).
    "Graph Disk Usage": "TRUE",
    # Monitor and graph System CPU Usage
    "Graph System CPU Usage": "TRUE",
    # Creates a graph of your system's memory usage.
    "Graph Memory Usage": "TRUE",
}


def main():
    sys_agents = get_config()
    sys_datatypes = get_agent_datatypes(sys_agents)
    get_agent_metrics(sys_datatypes)


def get_config():
    account_service = client['SoftLayer_Account']
    object_mask = "mask[id, maxMemory, maxCpu, datacenter.name, regionalGroup.name, " \
                  "operatingSystem.softwareLicense.softwareDescription.name, hostname, powerState," \
                  "blockDevices[device, id, diskImage[capacity, units]], monitoringAgents[id, name, configurationValues]]"
    masked_call = account_service.getVirtualGuests(mask=object_mask)
    sys_conf = {}
    sys_agents = {}
    for account in masked_call:
        account['datacenter'] = account['datacenter']['name']
        account['operatingSystem'] = account['operatingSystem']['softwareLicense']['softwareDescription']['name']
        account['regionalGroup'] = account['regionalGroup']['name']
        account['maxMemory'] = int(account['maxMemory']/1024)
        account['powerState'] = account['powerState']['name']
        drive_tag = 1
        for disk in account['blockDevices']:
            if 'diskImage' in disk.keys():  # assuming only relevant drives are disk drives
                d = disk['diskImage']
                if d['capacity'] >= 25 and d['units'] == 'GB':
                    account['drive_' + str(drive_tag) + '_id'] = disk['id']
                    account['drive_' + str(drive_tag) + '_capacity'] = (str(d['capacity']) + d['units'])
                    drive_tag += 1
        del account['blockDevices']  # drop duplicate info

        if account['monitoringAgents']:
            agents = [agent for agent in account['monitoringAgents'] if agent['name'] == agentName]
            if len(agents) != 0:
                sys_agents[account['id']] = agents[0]['configurationValues']
        account['monitoringAgents'] = bool(account['monitoringAgents'])

        fields = account.keys()
        sys_conf[account['id']] = list(account.values())

    df = DataFrame.from_dict(sys_conf, orient='index', columns=fields)
    df = df.drop('id', axis=1)
    df.index.name = 'id'
    df.to_csv("conf.csv")
    return sys_agents


def get_agent_datatypes(s_agents):
    agent_config_service = client['Monitoring_Agent_Configuration_Value']
    sys_datatypes = {}
    for vsi_id in s_agents.keys():
        metric_data_types = []
        for item in reports.keys():
            if reports[item].strip().upper() == 'TRUE':
                item_found = False
                for value in s_agents[vsi_id]:
                    if value['definition']['name'].strip().upper() == item.strip().upper():
                        item_found = True
                        if value['value'].strip().upper() == "TRUE":
                            try:
                                response = agent_config_service.getMetricDataType(id=value['id'])
                                metric_data_types.append(response)
                            except SoftLayer.SoftLayerAPIError as e:
                                print("Unable to get the metrics. " %(e.faultCode, e.faultString))
                        else:
                            print("The report: " + item +
                                  " is disable for the agent. Please review the agent configuration.")
                        break
                if not item_found:
                    print("The configuration: " + item + " is not available for the agent.")
        sys_datatypes[vsi_id] = metric_data_types
        sys_datatypes[vsi_id].append(s_agents[vsi_id][0]['agentId'])
    return sys_datatypes


def get_agent_metrics(s_datatypes):
    acc_data = {}
    for vsi_id in s_datatypes.keys():
        data = {}
        try:
            agent_id = s_datatypes[vsi_id].pop()
            response = client.call("Monitoring_Agent", "getGraphData", s_datatypes[vsi_id], metricStartDate, metricEndDate,
                               id=agent_id)
            if len(response) != 0:
                filter_data_points(data, response)
            else:  # if no value returned from api
                data['n/a'] = {'n/a': 'n/a'}
        except SoftLayer.SoftLayerAPIError as e:
            print("Unable to get the report: faultCode=%s, faultString=%s"
                  % (e.faultCode, e.faultString))
        acc_data[vsi_id] = data
    return acc_data


def get_metrics(acc_disks):
    metric_dict = {}
    metrics = ["cpu_utilization", "memory_usage", "disk_usage", "network_in", "network_out"]
    inst_disk_usage = get_disk_metrics_by_id(acc_disks)  # {vsi id: {disk id : {datetime : value}}}
    for virtual_id in acc_disks.keys():
        inst_metric_names = ('Cpu', 'Memory', 'DiskUsage', 'Bandwidth')
        inst_dict = {}
        for metric_name in inst_metric_names:
            #  Virtual_guest default metrics
            if metric_name == 'DiskUsage':
                response = inst_disk_usage[virtual_id]
            elif metric_name == 'Bandwidth':
                response = client.call('Virtual_Guest', 'getBandwidthDataByDate', metricStartDate, metricEndDate, id=virtual_id)
            else:
                response = client.call('Virtual_Guest', 'get' + metric_name + 'MetricDataByDate', metricStartDate, metricEndDate, id=virtual_id)
            if len(response) != 0:
                filter_data_points(inst_dict, response)
            else:  # if no value returned from api
                inst_dict['n/a'] = {'n/a': 'n/a'}

        for key, value in inst_dict.items():
            inst_dict[key] = Series(data=list(value.values()), index=value.keys())
        inst_ts = concat(inst_dict.values(), axis=1, keys=metrics)
        metric_dict[virtual_id] = inst_ts

    df = concat(metric_dict.values(), keys=acc_disks.keys(), sort=True)
    df.index.names = ['id', "dateTime"]
    df.to_csv("metric.csv")
    end = time.perf_counter()
    print(str(end - start))


# splits call returning metrics for 2+ types and appends {type : {datetime : data}} to input dict
def filter_data_points(curr_dict, response):
    curr_dict[response[0]['type']] = {}
    for data_point in response:  # populating inst dict with type : {time : value}
        if data_point['type'] not in curr_dict.keys():  # handling of multiple metrics returned
            curr_dict[data_point['type']] = {}
        curr_dict[data_point['type']][data_point['dateTime']] = data_point['counter']

def print_json(file):  # json output shortcut
    print(json.dumps(file, sort_keys=True, indent=2, separators=(',', ': ')))



if __name__ == '__main__':
    main()

#TODO Pass vsi agent id along to retrieval method