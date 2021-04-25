"""
Module that contains back end logic for orchestrating test + VM creation, execution, and teardown
"""
import config

import os
import csv
import sys
import logging
import json
import uuid
from datetime import datetime
from io import StringIO

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
from google.cloud import pubsub_v1

import mysql.connector

# When running in cloud environment, will inherit GCP credentials of service account associated with AppEngine
credentials = GoogleCredentials.get_application_default()
# GCP Python client library object that handles Compute Engine service calls
computeService = discovery.build('compute', 'beta', credentials=credentials)
# GCP Python client library object that handles Scheduler service calls
schedulerService = discovery.build('cloudscheduler', 'v1', credentials=credentials)
# GCP Python client library object that handles PubSub Publisher service calls
config.publisher = pubsub_v1.PublisherClient()
# GCP Python client library object that handles PubSub Subscriber service calls
config.subscriber = pubsub_v1.SubscriberClient()

# Variable that stores the parsed batch flags
batches = []
# Variable that stores the parsed VM image names
vms = []
# Variable that stores the user-defined maximum number of instances to be concurrently running
numMaxInstances = 0
# Variable that store the number of VM instances currently running
numCurrInstances = 0
# Dictionary that stores status information for each currently running VM (key --> name of instance)
instances = {}

# Placeholder for creating the flags for a test's payload execution
testCasePlaceholder = '-encr={} -trav={} -writing={} -ext={} -merg={} -mid={} -sleep={} -small={} -large={} -default={} '

# SQL statement to create the table where test cases are stored
createTableStatement = ('CREATE TABLE TestCasesTable('
                            'Id int NOT NULL AUTO_INCREMENT,'
                            'ExperimentName varchar(255) NOT NULL,'
                            'Batch TEXT,'
                            'VmImage varchar(255) NOT NULL,'
                            'TestFlags TEXT NOT NULL,'
                            'Status TEXT NOT NULL,'
                            'NumRetries TINYINT NOT NULL,'
                            'PRIMARY KEY (Id));')

# Placeholder SQL statement for inserting test case into DB table (associated with a given batch --> when user defines a specific test flag to test)
insertRowPlaceholderBatch = ('INSERT INTO TestCasesTable (ExperimentName, Batch, VmImage, TestFlags, Status, NumRetries) VALUES '
                            '(\'{}\', \'{}\', \'{}\', \'{}\', \'{}\', \'{}\');')
# Placeholder SQL statement for inserting test case into DB table (when user specifies ALL, no batches)
insertRowPlaceHolderNoBatch = ('INSERT INTO TestCasesTable (ExperimentName, VmImage, TestFlags, Status, NumRetries) VALUES '
                              '(\'{}\', \'{}\', \'{}\', \'{}\', \'{}\');')

# Placeholder SQL statement to find the test case ID and testFlags for a given VM image, test case status, and experiment
selectIdAndTestFlagsRow = "SELECT `Id`, `TestFlags` FROM `TestCasesTable` WHERE `VmImage`=%s AND `Status`=%s AND `ExperimentName`=%s"
# Placeholder SQL statement to update row in test cases table for a given test case ID to a given status
updateStatusRow = "UPDATE `TestCasesTable` SET `Status`=%s WHERE `Id`=%s"

# Placeholder SQL statement to find the number of times a given test case has been retried
selectNumRetriesRow = "SELECT `NumRetries` FROM `TestCasesTable` WHERE `Id`=%s"
# Placeholder SQL statement to update the number of times a given test case has been retried
updateNumRetriesRow = "UPDATE `TestCasesTable` SET `NumRetries`=%s WHERE `Id`=%s"

# Dictionary that maps flag key to possible flag values
flagDict = {'encr' : ['ASY', 'SYM'],
            'trav' : ['BFS', 'DFS', 'SUB'],
            'writing' : ['Yes', 'No', 'Tmp'],
            'ext' : ['Yes', 'No'],
            'merg' : ['Yes', 'No'],
            'mid' : ['Yes', 'No'],
            'sleep' : ['Yes', 'No'],
            'small' : ['Yes', 'No'],
            'large' : ['Yes', 'No'],
            'default' : ['Yes', 'No'],
            }

def cleanupInstanceAndImage(instanceName, schedulerName, vmImage):
    """
    Returns: whether or not there are any running instances
    Function that is called when there are no remaining test cases for instanceName running w/ image vmImage
    """
    global numCurrInstances
    # Delete instance
    deleteInstanceRequest = computeService.instances().delete(project=config.project_name, zone=config.zone, instance=instanceName)
    deleteInstanceResponse = deleteInstanceRequest.execute()
    config.logger.info("Deleted instance: {0}".format(instanceName))

    # Delete scheduler
    deleteScheduler(schedulerName, instanceName)

    # Remove entry w/ key from instance dictionary that keeps track of instance status
    del[instances[instanceName]]

    # Remove vmImage from list of vms
    if vmImage in vms:
        vms.remove(vmImage)
    # Decrement number of currently running instances by 1
    numCurrInstances = numCurrInstances - 1
    # Call launchVMs
    launchVMs(numMaxInstances)
    # If this is the last instance to be deleted and no further VMs were launched in launchVMs, return True
    if numCurrInstances == 0:
        return True
    else:
        return False


def deleteScheduler(schedulerName, instanceName):
    """
    Function that deletes scheduler w/ name schedulerName associated with an instance with name instanceName
    """
    deleteSchedulerRequest = schedulerService.projects().locations().jobs().delete(name=schedulerName)
    deleteSchedulerRequest.execute()
    config.logger.info("Deleted scheduler job: {0} for instance: {1}".format(schedulerName, instanceName))

def createScheduler(name):
    """
    Function that creates a scheduler job. This scheduler will
    publish to the host topic 20 minutes, signaling that a running instance w/
    name is in an error state and must be restarted + test case retried.
    """

    # Param that specifies where to create scheduler job
    parent = "projects/{0}/locations/{1}".format(config.project_name, config.location)
    # Param that specifies which topic to publish to on scheduler job execution
    hostTopic = "projects/{0}/topics/{1}".format(config.project_name, config.topic_name)

    # Replace placeholder values in createRestartJobBody.json w/ actual values
    job_body = {}
    with open('defaultJson/scheduler/createRestartJobBody.json') as json_file:
        job_body = json.load(json_file)

        job_body['pubsubTarget']['topicName'] = hostTopic
        job_body['pubsubTarget']['attributes']['vmName'] = name

        defaultSchedule = job_body['schedule']
        # Calculate time of scheduled job execution to be 20 minutes from now
        currTime = str((datetime.now().minute + 20) % 60).zfill(2)
        modifiedSchedule = defaultSchedule.replace('00', currTime, 1)
        job_body['schedule'] = modifiedSchedule

    # Create scheduler job
    schedulerRequest = schedulerService.projects().locations().jobs().create(parent=parent, body=job_body)
    schedulerResponse = schedulerRequest.execute()
    config.logger.info("Created scheduler w/ name: {0} for instance w/ name: {1}".format(schedulerResponse['name'], name))

    #Update scheduler name field in instances hashmap entry corresponding to instance w/ name
    instances[name][5] = schedulerResponse['name']

def resetInstance(name):
    """
    Function that restarts a currently running instance w/ name
    """
    resetRequest = computeService.instances().reset(project=config.project_name, zone=config.zone, instance=name)
    resetResponse = resetRequest.execute()
    config.logger.info("Reset instance w/ name: {0}".format(name))

def deleteTopic(topicName):
    """
    Function that deletes a topic with name topicName
    """
    topic_path = config.publisher.topic_path(config.project_name, topicName)
    config.publisher.delete_topic(request={"topic": topic_path})
    config.logger.info("Deleted topic with name: {0}".format(topicName))

def deleteSubscription(subName):
    """
    Function that deletes a subscription with name subName
    """
    subscription_path = config.subscriber.subscription_path(config.project_name, subName)
    config.subscriber.delete_subscription(request={"subscription": subscription_path})
    config.logger.info("Deleted subscription with name: {0}".format(subName))


def shutdown():
    """
    Raise: ValueError
    Function that signals end of experiment.
    """
    config.logger.info("All test cases are done running! Cleaning up")
    #Deleting host topic
    deleteTopic(config.topic_name)
    #Closing publisher
    config.publisher.stop()
    # Raises error for subscription monitoring thread in main.py to catch and close
    raise ValueError("Tests Complete!")


def subCallback(message):
    """
    Function that is the asynchronous callback function that the subscription is bound to.
    Thus, upon any PubSub message being published to the host topic, the message is passed into
    this function and processed.
    """

    # Grab the associated attribute that this message is for
    instanceName = message.attributes['vmName']
    config.logger.info("Message received for VM: {}".format(instanceName))

    # If status is present in message's attributes, then this came from the VM instance as opposed to the scheduled job.
    if 'status' in message.attributes:
        messageStatus = message.attributes['status']
        instanceList = instances[instanceName]
        vmImage, vmStatus, testId, testStatus, vmTopic, schedulerName = instanceList[0], instanceList[1], instanceList[2], instanceList[3], instanceList[4], instanceList[5]
        if vmStatus == 'LAUNCHING':
            # If vmStatus is launching, then message we should receive from vm after launch is READY
            if messageStatus != 'READY':
                config.logger.warning("messageStatus : {0} should be READY for instance: {1} with status LAUNCHING".format(messageStatus, instanceName))
            # Since this is VM is launching, we should not have assigned any of these values for this VM
            if testId is not None or testStatus is not None or vmTopic is not None:
                config.logger.warning("[testId, testStatus, vmTopic] should all be == None for instance: {0} with status LAUNCHING".format(instanceName))
            # Topic attribute should be set in message, so we know which topic to publish to for this VM
            if 'vmTopic' in message.attributes:
                vmTopic = message.attributes['vmTopic']
                instances[instanceName][4] = vmTopic
            else:
                config.logger.error("message should have attribute \'vmTopic\' set for instance: {0} with status LAUNCHING".format(instanceName))
                raise ValueError('Attribute \'vmTopic\' missing in PubSub message')
            # Find test cases in DB w/ status set to TO_START and VmImage set to vmImage
            cnx = getConnection()
            with cnx.cursor(dictionary=True, buffered=True) as cursor:
                cursor.execute(selectIdAndTestFlagsRow, (vmImage, 'TO_START', config.experimentName))
                result = cursor.fetchone()
                if result == None:
                    # If no test cases found, delete instance and associated entities & launch new VMs
                    config.logger.info("No remaining test cases for vmImage: {0}".format(vmImage))
                    deleteTopic(vmTopic)
                    deleteSubscription(vmTopic.replace("topic", "sub"))
                    # If cleanupInstanceAndImage returns true, numCurrInstances == 0
                    if cleanupInstanceAndImage(instanceName, schedulerName, vmImage):
                        # Must ack message before exiting otherwise will continue to be redelivered
                        message.ack()
                        shutdown()
                else:
                    # If test cases are found, grab first and publish to guest VM's topic w/ config.payload_name and flags
                    flags = result['TestFlags']
                    testCaseId = result['Id']
                    config.logger.info("Publishing message w/ data for testCaseId {0} to instanceName: {1}".format(testCaseId, instanceName))
                    # Publish message to VM topic w/ payload and testFlags
                    topic_path = config.publisher.topic_path(config.project_name, vmTopic)
                    config.publisher.publish(topic_path, b'NULL', payload=config.payload_name, testFlags=flags)
                    instances[instanceName][1] = 'RUNNING'
                    instances[instanceName][2] = testCaseId
                    instances[instanceName][3] = 'RUNNING'
                    # Update row in table w/ new testCase status
                    cursor.execute(updateStatusRow, ('RUNNING', testCaseId))
            cnx.close()
        # Case that VM was given a test case to run
        elif vmStatus == 'RUNNING':
            if messageStatus != 'DETECTED' and messageStatus != 'NOT_DETECTED':
                config.logger.warning("messageStatus : {0} should be DETECTED or NOT_DETECTED for instance: {1} with status READY".format(messageStatus, instanceName))
            if testId is None:
                config.logger.error("TestId should be non-null for vmStatus: {0}".format(vmStatus))
                raise ValueError('Property \'testId\' is None for VM that is currently running')
            # Update test case row in table w/ the given message's status
            cnx = getConnection()
            with cnx.cursor(dictionary=True, buffered=True) as cursor:
                cursor.execute(updateStatusRow, (messageStatus, testId))
            cnx.close()
            # Update map (vmStatus, testId, testStatus, vmTopic)
            instances[instanceName][1] = 'LAUNCHING'
            instances[instanceName][2] = None
            instances[instanceName][3] = None
            instances[instanceName][4] = None
            # Delete scheduler (for the finished test case that is now finished)
            deleteScheduler(schedulerName, instanceName)
            # Delete topic and subcription of VM
            deleteTopic(vmTopic)
            deleteSubscription(vmTopic.replace("topic", "sub"))
            # Reset instance
            resetInstance(instanceName)
            # Create scheduler (for new test case that will be assigned after reset)
            createScheduler(instanceName)
        # Must ack message before exiting otherwise will continue to be redelivered
        message.ack()
    # If status is not present in message's attributes, then this came from the scheduled job.
    else:
        instanceList = instances[instanceName]
        vmImage, vmStatus, testId, testStatus, vmTopic, schedulerName = instanceList[0], instanceList[1], instanceList[2], instanceList[3], instanceList[4], instanceList[5]
        if testId is None:
            config.logger.error("VM: {0} was never assigned a testId and has timed out.".format(instanceName))
        cnx = getConnection()
        with cnx.cursor(dictionary=True, buffered=True) as cursor:
            # One row should be returned from executed query (finding number of retries for given testId)
            numFound = cursor.execute(selectNumRetriesRow, (testId,))
            if numFound != 1:
                config.logger.error("One row should be found for vmStatus: {0}".format(vmStatus))
                raise ValueError('Row should have been found for currently running VM w/ assigned test case')
            result = cursor.fetchone()
            numRetries = result['NumRetries']
            numRetries = numRetries + 1
            # Increment number of retries by 1 and update row
            cursor.execute(updateNumRetriesRow, (numRetries, testId))
            # If we have reached maximum number of retries, then test should be marked as FAILED so as to be never attempted again
            if numRetries == config.max_retries:
                cursor.execute(updateStatusRow, ('FAILED', testCaseId))
            else:
                cursor.execute(updateStatusRow, ('TO_START', testCaseId))
            # Update map (vmStatus, testId, testStatus, vmTopic)
            instances[instanceName][1] = 'LAUNCHING'
            instances[instanceName][2] = None
            instances[instanceName][3] = None
            instances[instanceName][4] = None
            # Delete scheduler (for old test case that is now finished)
            deleteScheduler(schedulerName, instanceName)
            # Make sure topic is deleted (normally guest deletes but unsure in this state)
            deleteTopic(vmTopic)
            # Reset instance
            resetInstance(instanceName)
            # Create scheduler (for new test case that will be assigned after reset)
            createScheduler(instanceName)
        cnx.close()
        # Must ack message before exiting otherwise will continue to be redelivered
        message.ack()

def createTopicAndSub():
    """
    Function that creates the host topic and host subscription, using variables defined in config module.
    """
    topic_path = config.publisher.topic_path(config.project_name, config.topic_name)
    topic = config.publisher.create_topic(request={"name": topic_path})
    config.logger.info("Created topic: {}".format(topic.name))

    topic_name = 'projects/{0}/topics/{1}'.format(config.project_name, config.topic_name)
    subscription_name = 'projects/{0}/subscriptions/{1}'.format(config.project_name, config.sub_name)
    config.subscriber.create_subscription(name=subscription_name, topic=topic_name)
    config.future = config.subscriber.subscribe(subscription_name, subCallback)
    config.logger.info("Created subscription: {0} for topic: {1}".format(subscription_name, topic.name))

def launchVMs(numInstances):
    """
    Function that creates as many instances and associated scheduler jobs as possible under the numInstances threshold.
    """
    global numCurrInstances
    numMaxInstances = numInstances
    # The machine type of all instances
    machineType = "projects/{0}/zones/{1}/machineTypes/e2-medium".format(config.project_name, config.zone)
    # Only attempt to create more instances if numCurrInstances < numMaxInstances
    while numCurrInstances < numMaxInstances:
        # Inner loop that iterate over each vm in vms sequentially
        for vm in vms:
            # Create a unique instance ID
            name = vm + str(uuid.uuid4())[:6]
            # Initial status of instances entry for instance w/ name is 'LAUNCHING' and VM image of vm
            instances[name] = [vm, 'LAUNCHING', None, None, None, None]

            #Launch Instance w/ given name (name) and machine image (vm)
            sourceMachineImage = "projects/{0}/global/machineImages/{1}".format(config.project_name, vm)
            instance_body = {}
            with open('defaultJson/instances/createInstanceBody.json') as json_file:
                instance_body = json.load(json_file)
                instance_body['name'] = name
                instance_body['machineType'] = machineType
                instance_body['sourceMachineImage'] = sourceMachineImage

            # Create instance using computeService
            instanceRequest = computeService.instances().insert(project=config.project_name, zone=config.zone, body=instance_body)
            instanceResponse = instanceRequest.execute()
            config.logger.info("Created instance w/ name: {0} from image: {1}".format(name, vm))
            numCurrInstances += 1

            #Create scheduler job for instance
            createScheduler(name)

            # Exit for loop if threshold reached
            if numCurrInstances == numMaxInstances:
                break
        # Exit while loop if no instances are currently running
        if numCurrInstances == 0:
            break

def parseTestFlags(csvString):
    """
    Function that parses the user-input flags and appends each key,val pair to the variable batches
    """
    # Open generic StringIO reader handle
    f = StringIO(csvString)
    # Opens CSV reader w/ given StringIO handle
    batchReader = csv.reader(f)
    # Iterate over each csv in csvString
    for list in batchReader:
        for batch in list:
            # If user defined specific file directory for payload execution, store in config.rootPairString
            if batch.find(";") != -1:
                config.rootPairString = batch.strip();
            else:
                # Otherwise, further parse key, val flag entry and store in batches
                b = StringIO(batch)
                splitEntry = csv.reader(b, delimiter='=')
                for pair in splitEntry:
                    map(str.strip, pair)
                    batches.append(pair)

def parseVms(csvString):
    """
    Function that parses the user-input csv of vm images and appends to the variable vms
    """
    # Open generic StringIO reader handle
    v = StringIO(csvString)
    # Opens CSV reader w/ given StringIO handle
    vmReader = csv.reader(v)
    # Iterate over each vm
    for list in vmReader:
        for vm in list:
            # Remove extraneous whitespace and append to vms
            map(str.strip, vm)
            vms.append(vm)


def generateAllTests(experimentName):
    """
    Function that inserts every permutation of test flags for each VM image into DB table
    """
    # Get DB connection
    cnx = getConnection()
    # Get cursor object from connection
    with cnx.cursor(dictionary=True, buffered=True) as cursor:
        # Iterate over each value for each flag in flag dictionary
        for encrVal in flagDict['encr']:
            for travVal in flagDict['trav']:
                for writingVal in flagDict['writing']:
                    for extVal in flagDict['ext']:
                        for mergVal in flagDict['merg']:
                            for midVal in flagDict['mid']:
                                for sleepVal in flagDict['sleep']:
                                    for smallVal in flagDict['small']:
                                        for largeVal in flagDict['large']:
                                            for defaultVal in flagDict['default']:
                                                # Generate the test case flags from the current values in this loop iteration
                                                testFlags = testCasePlaceholder.format(encrVal, travVal, writingVal, extVal, mergVal, midVal, sleepVal, smallVal, largeVal, defaultVal) + config.rootPairString
                                                # Iterate over each vm image
                                                for vm in vms:
                                                    # Insert into table w/ status : TO_START and num_retries : 0
                                                    result = cursor.execute(insertRowPlaceHolderNoBatch.format(experimentName, vm, testFlags, 'TO_START', 0))
                                                    config.logger.debug(result)
    # Close DB connection
    cnx.close()

def generateBatchTestCases(batch, experimentName):
    """
    Function that creates the set of tests for a given test flag batch for
    an experiment with name experimentName.
    """
    encrList, travList, writingList, extList, mergList, midList, sleepList, smallList, largeList, defaultList = ([], ) * 10
    flag = batch[0]
    val = batch[1]
    # Determine which flag represents the batch. Use only the given value for the batch
    # Set the rest of the flags to be the default values in flagDict
    if flag == 'encr':
        encrList.append(val)
    else:
        encrList = flagDict['encr']
    if flag == 'trav':
        travList.append(val)
    else:
        travList = flagDict['trav']
    if flag == 'writing':
        writingList.append(val)
    else:
        writingList = flagDict['writing']
    if flag == 'ext':
        extList.append(val)
    else:
        extList = flagDict['ext']
    if flag == 'merg':
        mergList.append(val)
    else:
        mergList = flagDict['merg']
    if flag == 'mid':
        midList.append(val)
    else:
        midList = flagDict['mid']
    if flag == 'sleep':
        sleepList.append(val)
    else:
        sleepList = flagDict['sleep']
    if flag == 'small':
        smallList.append(val)
    else:
        smallList = flagDict['small']
    if flag == 'large':
        largeList.append(val)
    else:
        largeList = flagDict['large']
    if flag == 'default':
        defaultList.append(val)
    else:
        defaultList = flagDict['default']
    # Get DB connection
    cnx = getConnection()
    # Get cursor from DB connection
    with cnx.cursor(dictionary=True, buffered=True) as cursor:
        for encrVal in encrList:
            for travVal in travList:
                for writingVal in writingList:
                    for extVal in extList:
                        for mergVal in mergList:
                            for midVal in midList:
                                for sleepVal in sleepList:
                                    for smallVal in smallList:
                                        for largeVal in largeList:
                                            for defaultVal in defaultList:
                                                # Generate the test case flags from the current values in this loop iteration
                                                testFlags = testCasePlaceholder.format(encrVal, travVal, writingVal, extVal, mergVal, midVal, sleepVal, smallVal, largeVal, defaultVal) + config.rootPairString
                                                for vm in vms:
                                                    # Insert into table w/ batch set to flag + '=' + val and status : TO_START and num_retries : 0
                                                    sqlStatement = insertRowPlaceholderBatch.format(experimentName, flag + '=' + val, vm, testFlags, 'TO_START', 0)
                                                    cursor.execute(sqlStatement)
    # Close DB connection
    cnx.close()


def getConnection():
    """
    Return: mysql.connection
    Function that connects to MYSQL DB, using values defined in config module.
    """
    #First, connect to DB
    if os.environ.get('GAE_ENV') == 'standard':
        # If deployed, use the local socket interface for accessing Cloud SQL
        unix_socket = '/cloudsql/{}'.format(config.db_connection_name)
        return mysql.connector.connect(user=config.db_user, password=config.db_password,
                              unix_socket=unix_socket, db=config.db_name, autocommit=True)

    else:
        # If running locally, use the TCP connections instead
        # Set up Cloud SQL Proxy (cloud.google.com/sql/docs/mysql/sql-proxy)
        # so that your application can use 127.0.0.1:3306 to connect to your
        # Cloud SQL instance
        host = '127.0.0.1'
        return mysql.connector.connect(user=config.db_user, password=config.db_password,
                              host=host, db=config.db_name, autocommit=True)

def generateTestCases(vmsCsv, testFlagsCsv, experimentName):
    """
    Return: True upon successful generation
    Function that generates test cases for an experiment with given csvs for
    VM image names and test flags to run.
    """
    # Set config experimentName
    config.experimentName = experimentName
    parseVms(vmsCsv)
    cnx = getConnection()
    # Create TestCasesTable if not created
    with cnx.cursor(dictionary=True, buffered=True) as cursor:
        rows_count = cursor.execute('SELECT * FROM information_schema.tables WHERE table_schema = \'testCases\' AND table_name = \'TestCasesTable\' LIMIT 1;')
        if rows_count == 0:
            cursor.execute(createTableStatement)
    cnx.close()
    # If user wants to run ALL cases and not particular batches of test flags, run generateAllFlags
    if testFlagsCsv == 'ALL':
        generateAllTests(experimentName)
    # Otherwise, need to parse testFlagsCsv into batches and call generateBatchTestCases for each batch
    else:
        parseTestFlags(testFlagsCsv)
        for batch in batches:
            generateBatchTestCases(batch, experimentName)
    return True