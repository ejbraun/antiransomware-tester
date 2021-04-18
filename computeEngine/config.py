"""
Module that stores user-configured values for use during runtime
"""
# Project that this VM will be deployed in
project_name = '{PLACEHOLDER}'
# Messages are published to this topic name
host_topic = 'host_topic'
# Prefix for generating this VM topic name
topic = 'guest_topic'
# Prefix for generating this VM subscription name
sub = 'guest_sub'
# Instance name that is set after querying metadata server upon startup
instanceName = ''
# PubSub Python client library Publisher object
publisher = None
# PubSub Python client library Subscriber  object
subscriber = None
