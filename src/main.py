import SoftLayer
import config
from datetime import *
import time
from pandas import *
import json
import os
import argparse

#### performance testing
start = time.perf_counter()
calls = 0
####

parser = argparse.ArgumentParser()

parser.add_argument('-t', dest='hours', default='24',
                    help='amount of hours to receive data from')
args = parser.parse_args()
sampleSizeHours = int(args.hours)


client = SoftLayer.create_client_from_env(config.USERNAME, config.API_KEY)
project_root = os.path.abspath(os.path.join(__file__, "../.."))


dc_utc_offset = -5.00
now = (datetime.now(timezone(timedelta(hours=dc_utc_offset))))
now = now - timedelta(minutes=now.minute % 5, seconds=now.second, microseconds=now.microsecond)
dt_format = "%Y-%m-%dT%H:%M%z"
endDate = datetime.strftime(now, dt_format)
startDate = datetime.strftime(now - timedelta(hours=sampleSizeHours), dt_format)
id_host_map = {}
# Agent config parameters

agentName = 'Cpu, Disk, and Memory Monitoring Agent'
reports = {
    # Monitor and graph System CPU Usage
    "Graph System CPU Usage": "TRUE",
    # Creates a graph of your system's memory usage.
    "Graph Memory Usage as Percentage": "TRUE",
    # Create graphs for Disk Usage (in MB).
    "Graph Disk Usage": "TRUE",
}


def main():
    conf_df = get_config()
    conf_df.to_csv(project_root + os.path.sep + 'config.csv')

    attr_df = get_attributes()
    attr_df.to_csv(project_root + os.path.sep + 'attributes.csv')

    sys_agents = get_agents()
    sys_datatypes = get_agent_datatypes(sys_agents)
    metrics_df = get_agent_metrics(sys_datatypes)
    metrics_df = get_guest_metrics(metrics_df)
    metrics_df.to_csv(project_root + os.path.sep + 'workload.csv')

    end = time.perf_counter()
    print("took %ss to retrieve configuration info from %s vsi(s) and process %s hours of metrics for %s vsi(s).\n"
          "monitoring agents were accessible on %s%% of account systems." %
          ('{:.2f}'.format(end - start), str(len(list(conf_df.index))), sampleSizeHours,
           str(len(list(metrics_df.index.levels[0]))),
           '{:.0f}'.format(100*(len(list(metrics_df.index.levels[0]))/len(list(conf_df.index))))))


def get_config():
    print("getting config ...")

    object_mask = "mask[hostname, id, maxMemory, maxCpu, operatingSystem.softwareLicense.softwareDescription.name]"

    masked_call = client.call('Account', 'getVirtualGuests', mask=object_mask)
    acc_conf = {}
    df_keys = []

    for system in masked_call:
        sys_conf = {}
        sys_conf['host_name'] = system['hostname']
        sys_conf['HW Total CPUs'] = system['maxCpu']
        sys_conf['HW Total Memory'] = system['maxMemory']
        sys_conf['HW Manufacturer'] = 'IBM-Cloud'
        sys_conf['OS Version'] = system['operatingSystem']['softwareLicense']['softwareDescription']['name']
        if 'WINDOWS' in sys_conf['OS Version'].upper().strip():
            sys_conf['OS Name'] = 'Windows'
        else:
            sys_conf['OS Name'] = 'Linux'
        global id_host_map
        id_host_map[system['id']] = system['hostname']
        df_keys = sys_conf.keys()
        acc_conf[sys_conf['host_name']] = list(sys_conf.values())

    df = DataFrame.from_dict(acc_conf, orient='index', columns=df_keys)
    df = df.drop('host_name', axis=1)
    df.index.name = 'host_name'
    return df


def get_attributes():
    print("getting attributes ...")
    object_mask = "mask[hostname, id, primaryIpAddress, provisionDate, datacenter.name, regionalGroup.name, " \
                  "powerState, domain]"
    masked_call = client.call('Account', 'getVirtualGuests', mask=object_mask)
    acc_attr = {}
    for system in masked_call:
        sys_attr = {}
        sys_attr['host_name'] = system['hostname']
        sys_attr['Instance ID'] = system['id']
        sys_attr['Instance IP'] = system['primaryIpAddress']
        sys_attr['Launch Time'] = system['provisionDate']
        sys_attr['Virtual Cluster'] = system['datacenter']['name']
        sys_attr['Virtual Datacenter'] = system['regionalGroup']['name']
        sys_attr['virtual Domain'] = system['domain']
        sys_attr['Virtual Technology'] = 'IBM-Cloud'
        sys_attr['Power State'] = system['powerState']['name']
        df_keys = sys_attr.keys()
        acc_attr[sys_attr['host_name']] = list(sys_attr.values())

    df = DataFrame.from_dict(acc_attr, orient='index', columns=df_keys)
    df = df.drop('host_name', axis=1)
    df.index.name = 'host_name'
    return df


def get_drives():
    print("getting drives ...")
    object_mask = "mask[id, blockDevices[device, id, diskImage[capacity, units]]]"

    masked_call = client.call('Account', 'getVirtualGuests', mask=object_mask)
    acc_drives = {}
    for system in masked_call:
        sys_drives = {}
        drive_tag = 1
        for disk in system['blockDevices']:
            if 'diskImage' in disk.keys():  # assuming only relevant drives are disk drives
                d = disk['diskImage']
                if d['capacity'] >= 10 and d['units'] == 'GB':
                    sys_drives['drive_' + str(drive_tag) + '_id'] = disk['id']
                    sys_drives['drive_' + str(drive_tag) + '_capacity'] = (str(d['capacity']) + d['units'])
                    drive_tag += 1
        acc_drives[system['id']] = sys_drives


def get_agents():
    print("getting agents ...")
    sys_agents = {}
    response = client.call('Account', 'getVirtualGuests', mask='mask[monitoringAgents[id, name, configurationValues]]')
    for account in response:
        if account['monitoringAgents']:
            agents = [agent for agent in account['monitoringAgents'] if agent['name'] == agentName]
            if len(agents) != 0:
                sys_agents[account['id']] = agents[0]['configurationValues']
    return sys_agents


def get_agent_datatypes(s_agents):
    print("getting agent datatypes ...")
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
    print("getting agent metrics ...")
    acc_data = {}  # disk read is actually space used #TODO replace with correct
    metrics = {"CDM_CPU": "CPU Utilization", "CDM_MEMORY_PERC": "Memory Utilization",
               "CDM_DISK": "Disk Space Utilization"}  # TODO map datatype name to human readable

    for vsi_id in s_datatypes.keys():
        data = {}
        try:
            agent_id = s_datatypes[vsi_id].pop()
            response = client.call("Monitoring_Agent", "getGraphData", s_datatypes[vsi_id], startDate, endDate,
                                   id=agent_id)
            if len(response) != 0:
                filter_data_points(data, response)
            else:  # if no value returned from api
                data['n/a'] = {'n/a': 'n/a'}

        except SoftLayer.SoftLayerAPIError as e:
            print("Unable to get the report: faultCode=%s, faultString=%s"
                  % (e.faultCode, e.faultString))
        m_order = []
        # converting dict to series
        for key, value in data.items():
            data[key] = Series(data=list(value.values()), index=value.keys())
            m_order.append(metrics[key.upper().strip().split('_USAGE')[0]])
        inst_ts = concat(data.values(), axis=1, keys=m_order, sort=False)
        global id_host_map
        if vsi_id in id_host_map.keys():
            acc_data[id_host_map[vsi_id]] = inst_ts

    df = concat(acc_data.values(), keys=acc_data.keys(), sort=True)
    df.index.names = ['host_name', "Datetime"]
    return df


def get_guest_metrics(a_df):
    print("getting guest metrics ...")
    global id_host_map
    vsi_ids = []
    for vsi_id in list(id_host_map.keys()):
        if id_host_map[vsi_id] in list(a_df.index.levels[0]):
            vsi_ids.append(vsi_id)

    metric_dict = {}
    metrics = ("Raw Net Received Utilization", "Raw Net Sent Utilization")

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
        metric_dict[id_host_map[virtual_id]] = inst_ts

    df = concat(metric_dict.values(), keys=metric_dict.keys(), sort=True)
    df.index.names = ['host_name', "Datetime"]
    df = concat([df, a_df], axis=1)
    return df


# splits call returning metrics for 2+ types and appends {type : {datetime : data}} to input dict
def filter_data_points(curr_dict, response):
    curr_dict[response[0]['type']] = {}
    for data_point in response:  # populating inst dict with type : {time : value}
        if data_point['type'] not in curr_dict.keys():  # handling of multiple metrics returned
            curr_dict[data_point['type']] = {}
        data_point['dateTime'] = normalize_datetime(data_point['dateTime'])
        curr_dict[data_point['type']][data_point['dateTime']] = data_point['counter']


# rounds minute down to nearest multiple of 5, and sets second and
# millisecond values of time series to 0 to ensure proper concat
def normalize_datetime(dt_string):
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
