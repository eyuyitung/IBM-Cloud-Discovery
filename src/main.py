'''
    This is a prototype for IBM Cloud metric collection.

    Created on: 8/2/2018
    Last Update on: 8/24/2018

    Authors:
        Eric Yuyitung
        Stephen Newton
'''

# Import statements
import SoftLayer
from src import config
from datetime import *
import time
from pandas import *
import os
import argparse

# performance testing
start = time.perf_counter()
calls = 0
####

# Parsing in arguments from discovery.bat
parser = argparse.ArgumentParser()
parser.add_argument('-t', dest='hours', default='24',
                    help='amount of hours to receive data from')
parser.add_argument('-m', dest='midnight', default='Y',
                    help='start metric timeframe from utc midnight yesterday [Y/N] ')

args = parser.parse_args()
sampleSizeHours = int(args.hours)
midnight = bool(args.midnight.strip().upper() == 'Y')
# Declaring the client using login details
client = SoftLayer.create_client_from_env(config.USERNAME, config.API_KEY)
project_root = os.path.abspath(os.path.join(__file__, "../.."))

# Setting date and time ranges. is set based off of sampleSizeHours
dc_utc_offset = -5.00
now = (datetime.now(timezone(timedelta(hours=dc_utc_offset))))
now = now - timedelta(minutes=now.minute % 5, seconds=now.second, microseconds=now.microsecond)
utc_now = datetime.now(timezone.utc)
utc_midnight = utc_now - timedelta(hours=utc_now.hour, minutes=utc_now.minute + 5,
                                   seconds=utc_now.second, microseconds=utc_now.microsecond)
if midnight:
    input_time = utc_midnight
else:
    input_time = now
dt_format = "%Y-%m-%dT%H:%M%z"
endDate = datetime.strftime(input_time, dt_format)
startDate = datetime.strftime(input_time - timedelta(hours=sampleSizeHours), dt_format)

# Global variables
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


# Main execution block
def main():
    # call api for vsi config values, returns DataFrame
    conf_df = get_config()
    # export config DataFrame to csv and place in project root
    conf_df.to_csv(project_root + os.path.sep + 'config.csv')
    # call api for vsi attribute values, returns DataFrame
    attr_df = get_attributes()
    # export attribute DataFrame to csv and place in project root
    attr_df.to_csv(project_root + os.path.sep + 'attributes.csv')
    # call api to retrieve agent info, returns dict of available agents by vsi
    # {vsi_id:[agent1 conf, agent2 conf ..]}
    sys_agents = get_agents()
    # call api to retrieve available datatypes per agent per vsi, returns returns dict of list of dicts
    # {vsi_id1:[{agentdatatype1: info},{agentdatatype2: info} ...], vsi_id2 : ...}
    sys_datatypes = get_agent_datatypes(sys_agents)
    # inputs agent datatypes into api to retrieve available agent metrics per vsi, returns DataFrame
    workload_metric_df = get_agent_metrics(sys_datatypes)
    # calls api and retrieves additional metrics (ONLY for vsis which returned agent metric data ^),
    # concats horizontally with DataFrame returned by get_agent_metrics and returns updated DataFrame
    workload_metric_df = get_guest_metrics(workload_metric_df)
    # export metric workload DataFrame to csv and place in project root
    workload_metric_df.to_csv(project_root + os.path.sep + 'workload.csv')

    # script exec timer
    end = time.perf_counter()
    print("took %ss to retrieve configuration info from %s vsi(s) and process %s hours of metrics for %s vsi(s).\n"
          "monitoring agents were accessible on %s%% of account systems and metrics collected up until UTC midnight "
          "yesterday : %s" % ('{:.2f}'.format(end - start), str(len(list(conf_df.index))), sampleSizeHours,
           str(len(list(workload_metric_df.index.levels[0]))),
           '{:.0f}'.format(100*(len(list(workload_metric_df.index.levels[0]))/len(list(conf_df.index)))), str(midnight)))


# Gets the configuration values for a VSI (Name, ID, RAM, CPU, OS), returns DataFrame
def get_config():
    print("getting config ...")

    # Create data structures for holding conf info by vsi hostname and for holdiing DataFrame column headers
    acc_conf = {}
    df_keys = []

    # object mask applied to api call (limits and filters response)
    # more info @ https://softlayer.github.io/article/object-masks
    object_mask = "mask[hostname, id, maxMemory, maxCpu, operatingSystem.softwareLicense.softwareDescription.name]"
    masked_call = client.call('Account', 'getVirtualGuests', mask=object_mask)

    # for each vsi on account, copies desired info from api call to flattened dictionary
    for system in masked_call:
        sys_conf = {}
        sys_conf['host_name'] = system['hostname']
        sys_conf['HW Total CPUs'] = system['maxCpu']
        sys_conf['HW Total Memory'] = system['maxMemory']
        sys_conf['HW Manufacturer'] = 'IBM-Cloud'
        sys_conf['OS Version'] = system['operatingSystem']['softwareLicense']['softwareDescription']['name']

        # if os name contains "windows", sets to windows. otherwise defaults to linux
        if 'WINDOWS' in sys_conf['OS Version'].upper().strip():
            sys_conf['OS Name'] = 'Windows'
        else:
            sys_conf['OS Name'] = 'Linux'

        # populating global variable id_host_map
        global id_host_map
        id_host_map[system['id']] = system['hostname']

        # DataFrame column headers will be longest available set to avoid dropped data
        if len(df_keys) < len(sys_conf.keys()):
            df_keys = sys_conf.keys()

        # add dictionary entry of list of config values under host name
        acc_conf[sys_conf['host_name']] = list(sys_conf.values())

    df = DataFrame.from_dict(acc_conf, orient='index', columns=df_keys)
    # drop redundant column
    df = df.drop('host_name', axis=1)
    df.index.name = 'host_name'
    return df


# Gets the attribute values for a VSI (name, id, ip, launch time, region, data center, domain, power state)
# returns DataFrame
def get_attributes():
    print("getting attributes ...")
    # object mask applied to api call (limits and filters response)
    # more info @ https://softlayer.github.io/article/object-masks
    object_mask = "mask[hostname, id, primaryIpAddress, provisionDate, datacenter.name, regionalGroup.name, " \
                  "powerState, domain]"
    masked_call = client.call('Account', 'getVirtualGuests', mask=object_mask)

    # create data structure to hold vsi attributes by a vsi hostname and to hold DataFrame column headers
    acc_attr = {}
    df_keys = []
    # for each vsi on account, copies desired attribute value from api response to flattened dictionary
    for system in masked_call:
        sys_attr = {}
        sys_attr['host_name'] = system['hostname']
        sys_attr['Instance ID'] = system['id']
        sys_attr['Instance IP'] = system['primaryIpAddress']
        sys_attr['Launch Time'] = system['provisionDate']
        sys_attr['Virtual Cluster'] = system['datacenter']['name']
        sys_attr['Virtual Datacenter'] = system['regionalGroup']['name']
        sys_attr['virtual Domain'] = system['domain']
        # WARN setting to constant
        sys_attr['Virtual Technology'] = 'IBM-Cloud'
        sys_attr['Power State'] = system['powerState']['name']
        # avoiding dropped data due to missing headers
        if len(df_keys) < len(sys_attr.keys()):
            df_keys = sys_attr.keys()
        # list of attributes values stored under host name
        acc_attr[sys_attr['host_name']] = list(sys_attr.values())

    # convert dict to DataFrame
    df = DataFrame.from_dict(acc_attr, orient='index', columns=df_keys)
    # drop redundant column
    df = df.drop('host_name', axis=1)
    df.index.name = 'host_name'
    return df


# unused and untested
# returns dict of block devices by associated vsi
def get_drives():
    print("getting drives ...")
    object_mask = "mask[hostname, blockDevices[device, id, diskImage[capacity, units]]]"

    masked_call = client.call('Account', 'getVirtualGuests', mask=object_mask)
    acc_drives = {}
    for system in masked_call:
        sys_drives = {}
        drive_tag = 1
        for disk in system['blockDevices']:
            if 'diskImage' in disk.keys():  # assuming only relevant drives are disk drives
                d = disk['diskImage']
                # name and label formatting
                if d['capacity'] >= 10 and d['units'] == 'GB':
                    sys_drives['drive_' + str(drive_tag) + '_id'] = disk['id']
                    sys_drives['drive_' + str(drive_tag) + '_capacity'] = (str(d['capacity']) + d['units'])
                    drive_tag += 1
        acc_drives[system['hostname']] = sys_drives
    return acc_drives


# gets all agents and config values from vsi, returns dict of list of dict
# {vsi_id1: [{agentconf1: data}, {agentconf2: data}, ...], vsi_id2 : [...], ...}
def get_agents():
    print("getting agents ...")
    # create data structure holding agent conf by vsi id
    sys_agents = {}
    response = client.call('Account', 'getVirtualGuests', mask='mask[monitoringAgents[name, configurationValues]]')

    for account in response:
        if account['monitoringAgents']:
            agents = [agent for agent in account['monitoringAgents'] if agent['name'] == agentName]
            if len(agents) != 0:
                sys_agents[account['id']] = agents[0]['configurationValues']
    return sys_agents


# retrieve available datatypes given available agents
# {vsi_id1: [{agentconf1: data}, {agentconf2: data}, ...], vsi_id2 : [...], ...}
# returns dict of list of dicts same as ^ but cut down to only valid, desired datatypes
def get_agent_datatypes(s_agents):
    print("getting agent datatypes ...")
    # create convenience object
    agent_config_service = client['Monitoring_Agent_Configuration_Value']
    # create data structure to hold valid datatypes per system on provided credentials
    sys_datatypes = {}
    # for each vsi with agents enabled, call api for valid entries and store datatype
    for vsi_id in s_agents.keys():
        metric_data_types = []
        # iterate through desired metrics
        for item in reports.keys():
            if reports[item].strip().upper() == 'TRUE':
                item_found = False
                # iterate through agent conf entries
                for value in s_agents[vsi_id]:
                    # if agent conf entry 'name' matches desired metric name
                    if value['definition']['name'].strip().upper() == item.strip().upper():
                        item_found = True
                        # if metric is enabled on agent
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
        # add dict entry of available datatypes under vsi id
        sys_datatypes[vsi_id] = metric_data_types
        # add temp entry of agent id (popped from list in get_agent_metrics)
        sys_datatypes[vsi_id].append(s_agents[vsi_id][0]['agentId'])
    return sys_datatypes


# inputs datatypes into api to retrieve available agent metrics per vsi,
# returns DataFrame
def get_agent_metrics(s_datatypes):
    print("getting agent metrics ...")

    # create data structure to hold agent metric time series' per system
    acc_data = {}
    # dict to map densify headings to returned datatypes
    metrics = {"CDM_CPU": "CPU Utilization", "CDM_MEMORY_PERC": "Memory Utilization",
               "CDM_DISK": "Disk Space Utilization"}  # TODO update with properly mapped labels

    # call api and retrieve valid metrics for each vsi
    for vsi_id in s_datatypes.keys():
        # temp dict to hold agent metrics
        data = {}
        try:
            # pull agent id from list and call api with list of valid datatypes
            agent_id = s_datatypes[vsi_id].pop()
            response = client.call("Monitoring_Agent", "getGraphData", s_datatypes[vsi_id], startDate, endDate,
                                   id=agent_id)
            if len(response) != 0:
                # sort data points to {type:{datetime:value},...}
                filter_data_points(data, response)
            else:
                # if no value returned from api
                data['n/a'] = {'n/a': 'n/a'}

        except SoftLayer.SoftLayerAPIError as e:
            print("Unable to get the report: faultCode=%s, faultString=%s"
                  % (e.faultCode, e.faultString))
        # order of metrics returned
        m_order = []
        # converting dict to series
        for key, value in data.items():
            # populating metric order list
            m_order.append(metrics[key.upper().strip().split('_USAGE')[0]])
            # converting time series dict to pandas series
            data[key] = Series(data=list(value.values()), index=value.keys())

        # horizontally concat metric time series' for vsi to DataFrame
        inst_ts = concat(data.values(), axis=1, keys=m_order, sort=False)
        global id_host_map
        # map vsi_id to hostname and use hostname as key
        if vsi_id in id_host_map.keys():
            acc_data[id_host_map[vsi_id]] = inst_ts
    # vertically concat vsi metric dataframes
    df = concat(acc_data.values(), keys=acc_data.keys(), sort=True)
    # add index headers
    df.index.names = ['host_name', "Datetime"]
    return df


# retrieve additional metrics for vsi's with active agents, and adds to agent metric DataFrame
# returns DataFrame
def get_guest_metrics(a_df):
    print("getting guest metrics ...")

    # creating list of vsi ids
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
    # vertically concats vsi metric dataframes
    df = concat(metric_dict.values(), keys=metric_dict.keys(), sort=True)
    df.index.names = ['host_name', "Datetime"]
    # horizontally concats guest metrics to agent metrics
    df = concat([df, a_df], axis=1)
    return df


# splits response if returning metrics of 2+ types and appends {type : {datetime : data}} to curr dict
def filter_data_points(curr_dict, response):
    curr_dict[response[0]['type']] = {}
    for data_point in response:  # populating inst dict with type : {time : value}
        if data_point['type'] not in curr_dict.keys():  # handling of multiple metrics returned
            curr_dict[data_point['type']] = {}
        data_point['dateTime'] = normalize_datetime(data_point['dateTime'])
        curr_dict[data_point['type']][data_point['dateTime']] = data_point['counter']


# TODO fix sample start time issue instead of spoofing times (nimsoft agent config issue)
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


# ensure program is running as main process
if __name__ == '__main__':
    main()
