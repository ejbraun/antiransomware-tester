# antiransomware-tester

antiransomware-tester is a GCP deployed application that evaluates anti-ransomware effectiveness against specific ransomware behaviors.

To clone the project files from GitHub to a local directory:

    git clone https://github.com/ejbraun/antiransomware-tester.git

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

## System Architecture
### Host (App Engine)
#### Workflow
#### Design
### Guest (Compute Engine)
#### Design
## Setup

#### Project Creation
 1. Login to your Google account [here](https://cloud.google.com/).
 2. Click on *Console* at the top right of the page.
 3. After clicking through the various prompts, click on the dropdown *Select a project* at the top left of the page. Click on *New Project* at the top right of the prompt.
 4. Here you will be prompted to input your *Project name* and *Project ID* (`[PROJECT]`), which will be parameters used in the configuration files of the application.
 5.   Once the project has been created, you will be redirected to the newly created project's dashboard.
***
#### Cloud SQL 

 1. Click on *Activate Cloud Shell* icon in the top right corner of the page. It may take a moment to load.
 2. Execute `gcloud projects list`to see a table with headers *PROJECT_ID*, *NAME*, and *PROJECT NUMBER*.
 3. Locate the *PROJECT_ID* corresponding to the project you created in the previous section and execute `gcloud config set project <PROJECT_ID>`. Any future commands executed in this cloud shell will be in the context of this specific project.
 4. Click on the icon with three vertical dots with the hover-over message of *More* and select *Upload File*. Navigate to the cloned local directory with relative path  `scripts/`. Upload the file named `createSQLInstanceAndDB.sh`.
 5. After executing the command `ls`, you should see the file `createSQLInstanceAndDB.sh` in your current directory.
 6. Now, execute the script with the command `./createSQLInstanceAndDB.sh [INSTANCE_ID] [ROOT_PASSWORD] [USER_NAME] [DATABASE_NAME]`. 
 7. A prompt will appear asking you if you would like to enable the `sqladmin.googleapis.com`. Type `y` and press enter. The creation process will take a few minutes.
 8.  Once *Script execution complete* is displayed in the shell, refresh the page. Click on the *Navigation menu* at the top left of the page and click on *SQL* under *Databases*. An instance with *Instance ID* `[INSTANCE_ID]` should be visible and running. 
 9. Click on the entry in the table corresponding to `[INSTANCE_ID]`. In the redirected page, copy the text in the subheader *Connection name* under the header *Connect to this instance*. This value (`[CONNECTION_NAME]`) along with the above values (`[INSTANCE_ID] [ROOT_PASSWORD] [USER_NAME] [DATABASE_NAME]`) will be set in the `app.yaml`configuration in the **[Deployment](#deployment)** section.
 10. Stop the instance if you do not wish to incur charges while the application is not deployed.
***

#### Cloud Storage

 1. Click on the *Navigation menu* at the top left of the page and click on *Cloud Storage* under *Storage*.
 2. Click *Create Bucket*. Fill in the bucket name as `test-ovas`. The rest of the options should be filled based on user preference.
 3. After all of the options have been chosen, click *Create*.

***
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

 ****

####  Compute Engine

This section goes over how to setup a Windows VM with the project code, export as an .ova , upload to Cloud Storage, and create a Compute Engine machine image. 

A list of machine image names can then be input in the deployed web app and the VM lifecycles will subsequently be orchestrated by the back-end logic in `appEngine/host.py`.

Each image should only differ in the installed anti-ransomware program and the `readLogs()` method (since it is specific to each anti-ransomware program).

\*\*\* NOTE: Oracle VM VirtualBox Manager was used in the following steps \*\*\*
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

*Section: Deploying with Cloud SDK* 

\*\*\* NOTE: If you stopped the Cloud SQL instance, be sure to start it before deploying.\*\*\* 
 1. Navigate to `antiransomware-tester/appEngine`
 2. Execute the command `gcloud app deploy`
 3. Type `y` and press enter.
 4. Once the app is finished deploying, execute `gcloud app browse` to open the webpage in the default web browser.

If you wish to stop the application in App Engine:

 1. Click on the *Navigation menu* at the top left of the page and click on *App Engine* under *Serverless*. Click on *Settings* located in the left hand list of options.
 2. Click the blue button with text *Disable application*. Enter the name of the project and press enter to disable the application.  

