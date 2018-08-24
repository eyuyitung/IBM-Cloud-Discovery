# IBM-Cloud-Discovery
Python script for collection of IBM Cloud instance metrics and config data.

### Requirements
[Python 3.6.x](https://www.python.org/downloads/) (this program was written for 3.6.5 however)
Access to Cirba Analysis Console

## Getting Started

1. Install the dependencies via pip. The dependencies used thus far are defined in the [requirements.txt](requirements.txt) file
```
pip install -r requirements.txt
```
## Acquiring an API key
Login to https://control.softlayer.com with your account credentials. If you don't have any credentials, contact IT 
to have an account setup. 
   
 1. Go to your username in the top right of the screen and click on it.
 2. Once the page has loaded go to “API Access Information” near the bottom.
 3. There you should find your API username and Authentication Key. 
    If you don’t see your Authentication(API) Key, 
    then you need to generate one by clicking "generate".
 5. Paste the API Username into the USERNAME variable in src\config.py
 6. Paste the Authentication Key into the API_KEY variable in src\config.py
 7. If config.py does not exist, create the file, add the text below and populate as per steps 5 and 6.
```
  USERNAME = "replace-with-api-username"
  API_KEY = "replace-with-api-key"
```    
Now you should be able to run the script. 
Note: If you don't see any devices in your SoftLayer account then contact IT to
be given access to the test environment.

## Usage
1. Edit the PYDIR parameter in [Discovery.bat](Discovery.bat) to be the path to your Python.exe file. (default : C:\Program Files\Python36\Python.exe)
2. Open an administator instance of command prompt and navigate to the project folder
3. execute the script by entering ``` discovery.bat ``` and enter further information as prompted.	
4. Open Cirba Analysis Console and ensure the data has loaded properly.

## Notes
The timeframe of the dataset begins by default, n hours back from 23:55 UTC yesterday with samples every 5 minutes however changing the 
midnight parameter in [Discovery](Discovery.bat) to N, which will cause it to sample from the nearest 5 minute increment instead.
