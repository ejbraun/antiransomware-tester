"""
Module that stores user-configured values for use during runtime
"""

import google.cloud.logging
from google.cloud.logging.handlers import CloudLoggingHandler
import logging

# Username utilized to connect to DB (set in app.yaml)
db_user = ''
# Password used to login to DB (set in app.yaml)
db_password = ''
# Name of DB (set in app.yaml)
db_name = ''
# Connection name (set in app.yaml)
db_connection_name = ''
# GCP Project name (set in app.yaml)
project = ''
# GCP value for where certain cloud elements are physically located
zone = ''
# GCP value for where scheduler jobs are physically located
location = ''
# Payload file name that user uploads
payload_name = ''
# Name of PubSub host topic (unique)
topic_name = ''
# Name of PubSub host subscription (unique)
sub_name = ''
# User defined name of a particular experiment
experimentName = ''
# Where the mock ransomware payload is directed to begin execution
rootPairString = '-root=.\\files'
# Maximum number of retries allowed for a test before marked as failed
max_retries = 3
# Logging object
logger = None
# PubSub Host Subscriber object (pulls messages off sub_name)
subscriber = None
# PubSub Host Publisher object (publishes messages to various host VM topics)
publisher = None
# Future corresponding to asynchronous subscription callback (pulling messages off sub_name published by various VMs)
future = None

#Code used to setup GCP logger START
client = google.cloud.logging.Client()
handler = CloudLoggingHandler(client)
cloud_logger = logging.getLogger('cloudLogger')
#NOTE: Can set minimum log level here
cloud_logger.setLevel(logging.INFO) # normally defaults to WARN
cloud_logger.addHandler(handler)
logger = cloud_logger
#Code used to setup GCP logger END