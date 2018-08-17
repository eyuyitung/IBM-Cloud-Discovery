import SoftLayer
import config
from datetime import *
import time
from pandas import *
import json

#### performance testing
start = time.perf_counter()
print("start")
calls = 0
####

client = SoftLayer.create_client_from_env(config.USERNAME, config.API_KEY)

sampleSizeHours = 24
dc_utc_offset = -5.00
now = (datetime.now(timezone(timedelta(hours=dc_utc_offset))))
now = now - timedelta(minutes=now.minute % 5, seconds=now.second, microseconds=now.microsecond)
dt_format = "%Y-%m-%dT%H:%M%z"
endDate = datetime.strftime(now, dt_format)
startDate = datetime.strftime(now - timedelta(hours=sampleSizeHours), dt_format)
#endDate = now
#startDate = now - timedelta(hours=sampleSizeHours)

# Agent config parameters

agentName = 'Cpu, Disk, and Memory Monitoring Agent'
reports = {
    # Monitor and graph System CPU Usage
    "Graph System CPU Usage": "TRUE",
    # Creates a graph of your system's memory usage.
    "Graph Memory Usage": "TRUE",
    # Create graphs for Disk Usage (in MB).
    "Graph Disk Usage": "TRUE",
}


def main():
    conf_df = get_config()
    conf_df.to_csv('conf.csv')
    sys_agents = get_agents()
    sys_datatypes = get_agent_datatypes(sys_agents)
    metrics_df = get_agent_metrics(sys_datatypes)
    metrics_df = get_guest_metrics(metrics_df)
    metrics_df.to_csv('metrics.csv')
    end = time.perf_counter()
    print(str(end - start))
    print(calls)


def get_config():
    object_mask = "mask[id, maxMemory, maxCpu, datacenter.name, regionalGroup.name, " \
                  "operatingSystem.softwareLicense.softwareDescription.name, hostname, powerState," \
                  "blockDevices[device, id, diskImage[capacity, units]], " \
                  "monitoringAgents[id, name, configurationValues]]"

    masked_call = client.call('Account', 'getVirtualGuests', mask=object_mask)
    sys_conf = {}
    global calls
    calls += 1
    print("get config", calls)
    for account in masked_call:
        account['datacenter'] = account['datacenter']['name']
        account['operatingSystem'] = account['operatingSystem']['softwareLicense']['softwareDescription']['name']
        account['regionalGroup'] = account['regionalGroup']['name']
        account['maxMemory'] = int(account['maxMemory'] / 1024)
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
        account['monitoringAgents'] = bool(account['monitoringAgents'])
        fields = account.keys()
        sys_conf[account['id']] = list(account.values())

    df = DataFrame.from_dict(sys_conf, orient='index', columns=fields)
    df = df.drop('id', axis=1)
    df.index.name = 'id'
    return df


def get_agents():
    sys_agents = {}
    response = client.call('Account', 'getVirtualGuests', mask='mask[monitoringAgents[id, name, configurationValues]]')
    global calls
    calls += 1
    print("get_agents", calls)
    for account in response:
        if account['monitoringAgents']:
            agents = [agent for agent in account['monitoringAgents'] if agent['name'] == agentName]
            if len(agents) != 0:
                sys_agents[account['id']] = agents[0]['configurationValues']
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
                                global calls
                                calls += 1
                                print("get a data types", calls)
                                metric_data_types.append(response)
                            except SoftLayer.SoftLayerAPIError as e:
                                print("Unable to get the metrics. " % (e.faultCode, e.faultString))
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
    metrics = ("cpu_utilization", "memory_utilization", "disk_space_used")

    for vsi_id in s_datatypes.keys():
        data = {}
        try:
            agent_id = s_datatypes[vsi_id].pop()
            response = client.call("Monitoring_Agent", "getGraphData", s_datatypes[vsi_id], startDate, endDate,
                                   id=agent_id)
            global calls
            calls += 1
            print("get a metrics", calls)
            if len(response) != 0:
                filter_data_points(data, response)
            else:  # if no value returned from api
                data['n/a'] = {'n/a': 'n/a'}

        except SoftLayer.SoftLayerAPIError as e:
            print("Unable to get the report: faultCode=%s, faultString=%s"
                  % (e.faultCode, e.faultString))

        for key, value in data.items():
            data[key] = Series(data=list(value.values()), index=value.keys())
        inst_ts = concat(data.values(), axis=1, keys=metrics, sort=False)
        acc_data[vsi_id] = inst_ts

    df = concat(acc_data.values(), keys=acc_data.keys(), sort=True)
    df.index.names = ['id', "dateTime"]
    return df


def get_guest_metrics(a_df):
    vsi_ids = list(a_df.index.levels[0])
    metric_dict = {}
    metrics = ["network_in", "network_out"]

    # Loops through each VSI using a VSI ID grabbed from the account
    for virtual_id in vsi_ids:
        # Creates an instance dictionary each time a new VSI is found
        inst_dict = {}
        #  selects correct api call format
        response = client.call('Virtual_Guest', 'getBandwidthDataByDate', startDate, endDate, id=virtual_id)

        # Reformats API response and stores in inst_dict
        filter_data_points(inst_dict, response)

        # Converts metric dictionaries to time-series, concatenates horizontally, stores by VSI ID
        for key, value in inst_dict.items():
            inst_dict[key] = Series(data=list(value.values()), index=value.keys())
        inst_ts = concat(inst_dict.values(), axis=1, keys=metrics, sort=True)
        metric_dict[virtual_id] = inst_ts
    df = concat(metric_dict.values(), keys=vsi_ids, sort=True)
    df.index.names = ['id', "dateTime"]
    df = concat([df, a_df], axis=1)
    return df


# splits call returning metrics for 2+ types and appends {type : {datetime : data}} to input dict
def filter_data_points(curr_dict, response):
    curr_dict[response[0]['type']] = {}
    for data_point in response:  # populating inst dict with type : {time : value}
        if data_point['type'] not in curr_dict.keys():  # handling of multiple metrics returned
            curr_dict[data_point['type']] = {}
        data_point['dateTime'] = normalize_date_time(data_point['dateTime'])
        curr_dict[data_point['type']][data_point['dateTime']] = data_point['counter']


# rounds minute down to nearest multiple of 5, and sets second and
# millisecond values of time series to 0 to ensure proper concat
def normalize_date_time(dt_string):
    dt_string = dt_string[::-1].replace(':', '', 1)
    dt_string = dt_string[::-1]
    d_time = datetime.strptime(dt_string, "%Y-%m-%dT%H:%M:%S%z")
    dt_string = str(d_time - timedelta(minutes=d_time.minute % 5, seconds=d_time.second, microseconds=d_time.microsecond))
    dt_string = dt_string[::-1].replace(':', '', 1)
    dt_string = dt_string[::-1]
    return dt_string


def print_json(file):  # json output shortcut
    print(json.dumps(file, sort_keys=True, indent=2, separators=(',', ': ')))


if __name__ == '__main__':
    main()
