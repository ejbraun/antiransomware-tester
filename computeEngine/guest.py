"""
Module that contains PubSub creation + monitoring logic and payload execution + detection logic.
"""

import time
import uuid
import re
import requests
import subprocess

from google.cloud import pubsub_v1, storage
import google.api_core.exceptions

import config
"""REPLACE THIS IMPORT TO BE SPECIFIC TO VM IMAGE START"""
from monitorDefender import readLogs
"""REPLACE THIS IMPORT TO BE SPECIFIC TO VM IMAGE END"""

def getInstanceName():
    """
    Function that queries the internal metadata server for instance name.
    """
    response = requests.get('http://metadata.google.internal/computeMetadata/v1/instance/name',
                            headers={'Metadata-Flavor': 'Google'})
    config.instanceName = response.text

def subCallback(message):
    """
    Function that is the callback attached to the PubSub subscription. Processes messages
    sent from GCP AppEngine
    """
    if 'testFlags' in message.attributes and 'payload' in message.attributes:
        flagsToRunWith = message.attributes['testFlags']
        payloadName = message.attributes['payload']

        # Download Payload from Cloud Storage
        storage_client = storage.Client()
        bucket = storage_client.bucket("test-payloads")
        blob = bucket.blob(payloadName)
        blob.download_to_filename(payloadName)

        # Run as process and wait
        argsList = [payloadName]
        flagsToRunWith = flagsToRunWith.replace("root=.", "root=.\\")
        argsList.extend(flagsToRunWith.split())
        subprocess.run(argsList)

        # Run monitor log script specific to anti-malware program running on this VM
        detected = readLogs()
        if detected:
            vmStatus = 'DETECTED'
        else:
            vmStatus = 'NOT_DETECTED'

        # Publish to host
        topic_path = config.publisher.topic_path(config.project_name, config.host_topic)
        config.publisher.publish(topic_path, b'NULL', vmName=config.instanceName, status=vmStatus)
        print("Published message w/ status: {0} to host topic {1}".format(vmStatus, config.host_topic))

        # Teardown publisher and subscriber
        config.publisher.stop()
        print("stopped publisher")
        config.subscriber.close()
        print("closed subscriber")
    else:
        print("Received message from host without testFlags and/or payload set as attributes.")

def createTopicAndSub(genUID):
    """
    Return: google.cloud.pubsub_v1.subscriber.futures.StreamingPullFuture
    Function that creates topic and subscription for this VM instance.
    """
    # Create full names of topic and subscriptions
    config.topic = config.topic + genUID
    config.sub = config.sub + genUID

    topic_path = config.publisher.topic_path(config.project_name, config.topic)
    topic = config.publisher.create_topic(request={"name": topic_path})
    print("Created topic: {}".format(topic.name))

    topic_name = 'projects/{0}/topics/{1}'.format(config.project_name, config.topic)
    subscription_name = 'projects/{0}/subscriptions/{1}'.format(config.project_name, config.sub)
    config.subscriber.create_subscription(name=subscription_name, topic=topic_name)
    future = config.subscriber.subscribe(subscription_name, subCallback)
    print("Created subscription: {0} for topic: {1}".format(subscription_name, topic.name))
    return future

def startup():
    """
    Function that polls until GCP AppEngine host topic exists.
    """
    # Instantiate publisher and subscriper to relevant Python PubSub client library objects
    config.publisher = pubsub_v1.PublisherClient()
    config.subscriber = pubsub_v1.SubscriberClient()
    while True:
        topic_path = config.publisher.topic_path(config.project_name, config.host_topic)
        try:
            # Verify that the host_topic exists
            topic = config.publisher.get_topic(request={"topic": topic_path})
            break
        # If host topic does not exist, must wait until it does
        except google.api_core.exceptions.NotFound:
            print("Host topic does not exist.")
            time.sleep(10)


def running():
    """
    Function that polls until VM has sent host topic w/ result of anti-malware detection.
    """
    # Calls getInstanceName to discover name of instance
    getInstanceName()
    # Generate UID that will be appended to topic and subscription prefixes
    genUID = str(uuid.uuid4())[:6]
    # Store subscription future to be polled later
    future = createTopicAndSub(genUID)

    # Publish message to host_topic w/ status READY
    vmStatus = 'READY'
    print("Publishing message w/ status: {0} to host topic {1}".format(vmStatus, config.host_topic))
    topic_path = config.publisher.topic_path(config.project_name, config.host_topic)
    config.publisher.publish(topic_path, b'NULL',vmName=config.instanceName, status=vmStatus, vmTopic=config.topic)
    numRetries = 0
    while True:
        try:
            print("Polling subscription")
            future.result()
            break
        # Prevents delay of subscription creation from crashing program
        except google.api_core.exceptions.NotFound:
            print("Subscription creation has not propagated yet")
            numRetries = numRetries + 1
            if numRetries == 5:
                raise
            time.sleep(5)
        # Unexpected error encountered
        except Exception as e:
            print("Shutting down")

def mainFunc():
    startup()
    running()

if __name__ == '__main__':
    mainFunc()
