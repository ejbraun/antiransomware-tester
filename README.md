# antiransomware-tester

antiransomware-tester is a GCP deployed application that allows users to test the effectiveness of various anti-ransomware programs against specific ransomware behaviors in a timely and cost-effective manner.

To clone the project files from GitHub to a local directory:

    git clone https://github.com/ejbraun/antiransomware-tester.git
    
## File Directory Structure

File directory structure is as follows:

 - `antiransomware-tester/`
	 - `appEngine/` --> files used in App Engine
		 - `defaultJson/`--> JSON template files used for various Google Cloud API service calls
			 - `instances/`  
				 - `createInstanceBody.json`
			 - `scheduler/`
				 - `createRestartJobBody.json`
		 - `templates/` --> pages served by App Engine
			 - `monitoring.html`
			 - `registration.html`
		 - `app.yaml` --> configuration
		 - `config.py` --> configuration
		 - `main.py` --> Flask logic
		 - `host.py` --> back-end logic
		 - `model.py` 
		 - `requirements.txt` --> dependency list
	 - `computeEngine/`--> files used in setup of VM instances
		 - `config.py`--> configuration
		 - `guest.py` --> back-end logic
		 - `monitorDefender.py` --> detection event parser specific to Windows Defender
		 - `wrapper.py`
	 - `scripts/`
		 - `createSQLInstanceAndDB.sh` --> shell script to setup Cloud SQL in GCP

## Video of Example Workflow

[![Workflow Demo](https://i.imgur.com/IZE4qds.png)](https://youtu.be/TgZS4wAQ9AA "Workflow Demo")

## System Architecture

### Experiment Setup / Creation

After the application is deployed and the user navigates to the webpage in a browser, a form is displayed:
 
![image](https://user-images.githubusercontent.com/32010183/116004489-19cb7480-a5c0-11eb-8ac1-67737b4ee3bd.png)

Here, the user can specify:
 - which anti-ransomware program they would like to test (corresponding to a specific VM image)
 - specific behaviors they would like to test
 - the maximum number of concurrently running VM instances
 - the experiment name
 - upload the payload

The intended payload used in this system was developed in the paper [Prognosis Negative: Evaluating Real-Time Behavioral Ransomware Detectors](https://www.ieee-security.org/TC/EuroSP2021/accepted.html). It is a mock ransomware payload that allows the user to emulate various behaviors of ransomware through flags. A list explaining each of these flags and potential values is visible on the webpage.

After the user is finished specifying the experiment parameters and clicks *Submit*, the following occurs:

 ![image](https://user-images.githubusercontent.com/32010183/116005119-cd356880-a5c2-11eb-9761-26dbb0ec81bc.png)

The back-end logic of the application running in App Engine creates and inserts all of the permutations of the test cases to run into the Cloud SQL table in GCP. The specified payload is also uploaded to Cloud Storage in GCP.

The application then sets up its [PubSub](https://cloud.google.com/pubsub/docs/quickstart-client-libraries) messaging structure. It creates a topic named `host_topic` and subscribes to messages sent to `host_topic` with a subscription named `host_sub`. Detection results for each test will be sent in a PubSub message from a given VM instance to `host_topic`.

The application will then go through the list of VM images provided by the user and spawn Compute Engine instances up to the specified maximum number of instances. For example, if the user provides the list of images `defender_image, norton_image,  cryptodrop_image` and the maximum number of instances as 2, then the application will launch one VM instance from image `defender_image` and one VM instance from `norton_image`.

After the initial launch of VMs is complete, the user will be redirected to the following page:

![image](https://user-images.githubusercontent.com/32010183/116005736-8b59f180-a5c5-11eb-90ae-87e22d8ca389.png)

Here, the user can monitor the status of all the tests in the experiment while it is running.

### Experiment Execution

When a Compute Engine instance is launched, it will create its own PubSub messaging structure of a topic named `guest_topic{ID}` and subscription `guest_sub{ID}`. The instance will then publish a message to `host_topic` with a payload of `name: instance-name{ID}` and `topic: guest_topic{ID}`. The application will receive this message (through its subscription `host_sub`) and determine which VM image `instance-name{ID}` is running on. The app will then search the SQL table of test cases for tests with status `TO_START`and the same VM image. 

If a non-zero amount of test cases are found, then it will select the first test case and publish a message to   `guest_topic{ID}` with a payload of `payload_name: uploaded_filename` and `testFlags: selectedTestCaseFlags`. 

The Compute Engine instance will receive this message (through its subscription `guest_sub{ID}`) and download the payload with name `uploaded_filename` from Cloud Storage. It will then execute the payload with the given `testFlags` and determine whether or not the anti-ransomware detected the payload. The instance will then publish a message to `host_topic` with a payload of `detection: detectionResult (True or False)` and `name: instance-name{ID}`. 

The application will receive this detection result message and update the corresponding entry in the test cases table with `Status=detectionResult`. The VM instance with name `instance-name{ID}` will then be [reset](https://cloud.google.com/compute/docs/reference/rest/v1/instances/reset) and the process will start over from the beginning.

If zero test cases are found for a given VM image (and by extension, a given VM instance), then the VM instance will be deleted. Since this reduces the number of currently running VM instances by one, the application will then attempt to iterate through the list of VM images and spawn a new instance for a VM image which still has test cases to run. 

##### An Aside On Test Case Redundancy

A feature exists to limit the number of attempts for buggy and problematic test cases.

Upon either the creation or resetting of a VM instance, an associated Cloud Scheduler job is created for the instance. This job is scheduled to publish a message to `host_topic` 20 minutes from creation/resetting and contains only the instance name in its payload. The job is deleted if either the instance publishes a detection result message for its assigned test case or if there are zero remaining test cases for its VM image.

If neither of the above conditions are true, then the application will receive the job's published message, increment the value of `NumRetries` by 1 for the instance's assigned test case, and reset the instance. If `NumRetries` is less than three, then the status of the test case will be changed back to `TO_START`. If the `NumRetries` is equal to three, then the test case will be changed to `FAILED` and will be never be attempted again.


### Experiment Teardown

If zero test cases with status `TO_START` are found for *any* given image, then the experiment is completed. The application can then delete its PubSub `host_topic` and `host_sub`. All Compute Engine instances will have deleted their associated PubSub topics and subscriptions as well. 

No experiment resources aside from the uploaded payload in Cloud Storage and inserted entries in the MySQL table in Cloud SQL will remain in GCP.

The user can now query the data stored in the MySQL test cases table to evaluate the chosen anti-ransomware programs performance against specific ransomware behaviors.

## Setup

#### Project Creation

 1. Login to your Google account [here](https://cloud.google.com/).
 2. Click on *Console* at the top right of the page.
 3. After clicking through the various prompts, click on the dropdown *Select a project* at the top left of the page. Click on *New Project* at the top right of the prompt.
 4. Here you will be prompted to input your *Project name* and *Project ID* (`[PROJECT]`), which will be parameters used in the configuration files of the application.
 5.   Once the project has been created, you will be redirected to the newly created project's dashboard.

#### Cloud SQL 

 1. Click on *Activate Cloud Shell* icon in the top right corner of the page. It may take a moment to load.
 2. Execute `gcloud projects list`to see a table with headers *PROJECT_ID*, *NAME*, and *PROJECT NUMBER*.
 3. Locate the *PROJECT_ID* corresponding to the project you created in the previous section and execute `gcloud config set project <PROJECT_ID>`. Any future commands executed in this cloud shell will be in the context of this specific project.
 4. Click on the icon with three vertical dots with the hover-over message of *More* and select *Upload File*. Navigate to the cloned local directory with relative path  `scripts/`. Upload the file named `createSQLInstanceAndDB.sh`.
 5. After executing the command `ls`, you should see the file `createSQLInstanceAndDB.sh` in your current directory.
 6. Now, execute the script with the command `./createSQLInstanceAndDB.sh [INSTANCE_ID] [ROOT_PASSWORD] [USER_NAME] [DATABASE_NAME]`. 
 7. A prompt will appear asking you if you would like to enable the `sqladmin.googleapis.com`. Type `y` and press enter. The creation process will take a few minutes.
 8.  Once *Script execution complete* is displayed in the shell, refresh the page. Click on the *Navigation menu* at the top left of the page and click on *SQL* under *Databases*. An instance with *Instance ID* `[INSTANCE_ID]` should be visible and running. 
 9. Click on the entry in the table corresponding to `[INSTANCE_ID]`. In the redirected page, copy the text in the subheader *Connection name* under the header *Connect to this instance*. This value (`[CONNECTION_NAME]`) along with the above values (`[INSTANCE_ID] [ROOT_PASSWORD] [USER_NAME] [DATABASE_NAME]`) will be set in the `app.yaml`configuration in the **[Configuration Modification](#configuration-modification)** section.
 10. Stop the instance if you do not wish to incur charges while the application is not deployed.

#### Cloud Storage

 1. Click on the *Navigation menu* at the top left of the page and click on *Cloud Storage* under *Storage*.
 2. Click *Create Bucket*. Fill in the bucket name as `test-ovas`. The rest of the options should be filled based on user preference.
 3. After all of the options have been chosen, click *Create*.

#### App Engine

 1. Click on the *Navigation menu* at the top left of the page and click on *App Engine* under *Serverless*. Click on the blue button with text *Create Application*.
 2. Select the region that you want your application to be located in. This is a parameter that will be used in the configuration files of the application (`[LOCATION]`).
 3. Next, choose *Python* as the *Language* and keep *Standard* as the *Environment*.
 
 ***
#### Configuration Modification

The only file needed to be modified in `appEngine` is `appEngine/app.yaml`

 1. Open the `antiransomware-tester/appEngine/app.yaml`file in your
    favorite text editor.
 2. Replace the values as follows:
	 - `CLOUD_SQL_USERNAME`---> `[USER_NAME]`
	 - `CLOUD_SQL_PASSWORD`---> `[ROOT_PASSWORD]`
	 - `CLOUD_SQL_CONNECTION_NAME`---> `[CONNECTION_NAME]`
	 - `CLOUD_SQL_DATABASE_NAME`---> `[DATABASE_NAME]`
	 - `PROJECT_NAME`---> `[PROJECT]`
	 - `ZONE`---> Choose from the list located  [here](https://cloud.google.com/compute/docs/regions-zones#available) (*zone* is where the Compute Engine VMs will be deployed)
	 - `LOCATION`---> `[LOCATION]`

***
####  Compute Engine

\*\*\* NOTE: Oracle VM VirtualBox Manager was used in this section. \*\*\*

This section goes over how to setup a Windows VM with the project code, export as an .ova , upload to Cloud Storage, and create a Compute Engine machine image. 

A list of machine image names can then be input in the deployed web app and the VM lifecycles will subsequently be orchestrated by the back-end logic in `appEngine/host.py`.

Each image should only differ in the installed anti-ransomware program and the `readLogs()` method (since it is specific to each anti-ransomware program).

##### Base Windows VM Setup

 1. Download a Windows 10 virtual machine image ([link](https://developer.microsoft.com/en-us/microsoft-edge/tools/vms/)) and extract the .ova file.
 2. Follow the .ova import process described [here](https://docs.oracle.com/cd/E26217_01/E26796/html/qs-import-vm.html).
 3. Launch the VM and login.
 4. Install Python 3.9 ([here](https://www.python.org/downloads/)).
 5. Copy the files located in the `antiransomware-tester/computeEngine/` folder to a folder of your choice inside the VM (e.g. `Documents/`).
 6. Launch a command prompt, `cd` to the chosen directory, and install the required dependencies with the command `pip install -r requirements.txt`.
 7. Create a folder named `files` . Place the files that you wish to encrypted by the mock ransomware every test inside of this folder. An example source can be found [here](https://digitalcorpora.org/corpora/files).
 8. Create a shortcut of `wrapper.py`. Move the shortcut to `C:\Users\[USER]\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`, replacing`[USER]` with the correct value.
 9.  Press the Windows key and type *netplwiz*, subsequently clicking on the suggested item *netplwiz*. 
 10. Uncheck the box next to *Users must enter a user name and password to use this computer*. A prompt will appear, asking you to input the password and to confirm.
 11. Restart the virtual machine.  
 12. Take a snapshot.

#####  Specific Anti-Ransomware Setup

The file `computeEngine/monitorDefender.py` is used to determine whether or not Windows Defender detected the mock ransomware attack. Thus, in order to test a different anti-ransomware that is not Windows Defender, you must:

 1. Starting from the snapshot taken at the end of the previous section, install the anti-ransomware on the VM. 
 2.  Replace the body of `readLogs()` inside `monitorDefender.py` with logic that works for detecting events from the chosen anti-ransomware program. Rename the file if you desire. 
 3. If the file has been renamed, change the module name after the `from` keyword in the import statement on Line 16 of `guest.py`.
 4.  Take a snapshot.

##### Ova Export

For each anti-ransomware snapshot you create, you need to:

 1. Inside Oracle VM VirtualBox Manager, click on *File* and the option *Export Appliance...* in the resulting dropdown.
 2. Choose the virtual machine you would like to export and follow the instructions. The default options are all okay.

#####  Upload to Cloud Storage

For each .ova you create,  execute the following command in your local shell:

`gsutil cp "[ABSOLUTE_PATH_TO_FILE]\[FILE_NAME].ova" gs://test-ovas/[FILE_NAME].ova`

#####  Machine Image Creation

For each uploaded .ova, execute the following command in your local shell:

`gcloud beta compute machine-images import [IMAGE_NAME] --source-uri="gs://test-ovas/[FILE_NAME].ova" --os=windows-10-x64-byol`, where `[IMAGE_NAME]` is the name you wish to give to the machine image.

## Deployment

\*\*\* NOTE: If you stopped the Cloud SQL instance, be sure to start it before deploying.\*\*\* 

 1. Navigate to `antiransomware-tester/appEngine`
 2. Execute the command `gcloud app deploy`
 3. Type `y` and press enter.
 4. Once the app is finished deploying, execute `gcloud app browse` to open the webpage in the default web browser.

If you wish to stop the application in App Engine:

 1. Click on the *Navigation menu* at the top left of the page and click on *App Engine* under *Serverless*. Click on *Settings* located in the left hand list of options.
 2. Click the blue button with text *Disable application*. Enter the name of the project and press enter to disable the application.  


