pipumpkin
=========
This is a python program which accepts text-to-speech requests uploaded to a twitter account and plays them out using espeak/pyttsx.
It is planned to be placed inside a pumpkin for office use only. Enjoy!

Make it yourself
================
You'll need:
* A Raspberry Pi
* A speaker system. Battery or USB-powered speakers can be embedded more easily!
* A twitter account to be used as a "speech queue"

Set-up
======
* Check-out the code on your raspberry pi
* Create a twitter account and an application (e.g. I used https://twitter.com/pipumpkin). Note the access tokens.
* Run setup/setup to install and download all the necessary packages.
* Add the tokens to a json file in /etc/
