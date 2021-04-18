#!bin/python
""" Module that sets config module variables and runs Flask application """
from flask import Flask, request, render_template, redirect, url_for
from model import RegForm
from flask_bootstrap import Bootstrap
from werkzeug.utils import secure_filename
import os
import mysql.connector
import config
from host import generateTestCases, createTopicAndSub, launchVMs, getConnection
from google.cloud import storage
from google.api_core.exceptions import NotFound
import logging
import threading


# Assign config module variables from environment variables START
config.db_user = os.environ.get('CLOUD_SQL_USERNAME')
config.db_password = os.environ.get('CLOUD_SQL_PASSWORD')
config.db_name = os.environ.get('CLOUD_SQL_DATABASE_NAME')
config.db_connection_name = os.environ.get('CLOUD_SQL_CONNECTION_NAME')
config.project_name = os.environ.get('PROJECT_NAME')
config.zone = os.environ.get('ZONE')
config.location = os.environ.get('LOCATION')
config.topic_name = os.environ.get('TOPIC_NAME')
config.sub_name = os.environ.get('SUB_NAME')
# Assign config module variables from environment variables END

# Placeholder query used to populate monitoring page table w/ status of current tests
selectRows = "SELECT * FROM `TestCasesTable` WHERE `ExperimentName`=%s"

# Flask setup START
app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=b'\xd6\x04\xbdj\xfe\xed$c\x1e@\xad\x0f\x13,@G')
Bootstrap(app)
# Flask setup END

@app.route('/', methods=['GET', 'POST'])
def registration():
    """
    Default route
    Handles form input validation
    Redirects to monitoring page after experiment starts
    """
    # Instantiates RegForm form (defined in model.py)
    form = RegForm()
    # Conditional that checks if user is trying to submit form, all input values are valid, and successful generation of test cases to be run
    if request.method == 'POST' and form.validate_on_submit() and generateTestCases(form.vm_csv.data, form.test_flags_csv.data, form.experiment_name.data):
        # Instantiate GCP storage client object
        storage_client = storage.Client()
        try:
            # Attempt to get bucket with name 'test-payloads'
            bucket = storage_client.get_bucket("test-payloads")
        except NotFound:
                # If bucket 'test-payloads' does not exist, then create it
                newBucket = storage_client.bucket("test-payloads")
                newBucket.storage_class = "COLDLINE"
                bucket = storage_client.create_bucket(newBucket, location="us")
        # Grab the actual file uploaded to form
        p = form.file_field.data
        # Bucket corresponding to 'test-payloads'
        bucket = storage_client.bucket("test-payloads")
        # Create blob with same name as filename
        blob = bucket.blob(p.filename)
        # Upload the file to GCP Storage
        blob.upload_from_string(p.read(), content_type=p.content_type)
        # Set config module's payload_name to be the same as the filename
        config.payload_name = p.filename
        config.logger.info('Successfully uploaded payload w/ name: {0} in bucket {1}'.format(config.payload_name, "test-payloads"))
        # Call function that creates the PubSub host topic and subscription (located in host.py)
        createTopicAndSub()
        # Call function that launches VMs corresponding to user-defined form value of maximum number of VM instances
        launchVMs(form.num_instances.data)
        # Thread that closes subscriber once experiment is done running
        subThread = threading.Thread(target=subscriptionMonitor)
        # Start running thread
        subThread.start()
        # Redirect user to monitoring page (can view test case status')
        return redirect(url_for('monitoring'))
    # If HTTP request was a GET, then return rendered form (form declaration found in model.py)
    return render_template('registration.html', form=form)

def subscriptionMonitor():
    """
    Function that monitors future (corresponding to PubSub subscription callback)
    """
    try:
        # Blocking call
        config.future.result()
    # Experiment is done and must close subscription
    except Exception as e:
        config.logger.info("Main.py caught error {0}".format(e))
        # Closing host subscription
        subscription_path = config.subscriber.subscription_path(config.project_name, config.sub_name)
        with config.subscriber:
            config.subscriber.delete_subscription(request={"subscription": subscription_path})
        config.logger.info("Deleted host subscription with name: {0}".format(config.sub_name))

@app.route('/monitoring')
def monitoring():
    """
    Function that displays test case status in a table
    """
    # Get a connection to DB
    cnx = getConnection()
    # Declare data variable
    data = []
    # Create cursor object
    with cnx.cursor(buffered=True) as cursor:
        #Execute SELECT query to grab all rows from DB corresponding to currently running experiment
        cursor.execute(selectRows, (config.experimentName,))
        # Fetch all of the rows from query
        data = cursor.fetchall()
    # Close connection
    cnx.close()
    # Render monitoring template (in templates/), passing data variable to populate table rows
    return render_template('monitoring.html', data=data)

if __name__ == '__main__':
    app.run()
