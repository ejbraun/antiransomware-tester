"""
Module that contains function readLogs() for a VM instance testing Monitor Defender.
Adapted from https://stackoverflow.com/a/65417608
"""
import win32evtlog
import xml.etree.ElementTree as ET

def readLogs():
    """
    Return: True if Monitor Defender detected malware, False otherwise
    Function that reads Monitor Defender logs and counts number of Level 3 events.
    """
    # Open Event File
    query_handle = win32evtlog.EvtQuery(
        'C:\Windows\System32\winevt\Logs\Microsoft-Windows-Windows Defender%4Operational.evtx',
        win32evtlog.EvtQueryFilePath)
    read_count = 0
    while True:
        # Read 100 records
        events = win32evtlog.EvtNext(query_handle, 100)
        # If there are no records present in the loop, break
        if len(events) == 0:
            break
        for event in events:
            # Grab XML content from
            xml_content = win32evtlog.EvtRender(event, win32evtlog.EvtRenderEventXml)
            # Parse XML content
            xml = ET.fromstring(xml_content)
            # Define namespace
            ns = '{http://schemas.microsoft.com/win/2004/08/events/event}'
            # Find level in log
            level = xml.find(f'.//{ns}Level').text
            # Level 3 corresponds to detection event
            if level == '3':
                read_count += 1
    # If any level 3 events were found, return true (DETECTED)
    if read_count > 0:
        return True
    else:
        # Return False (NOT DETECTED)
        return False
