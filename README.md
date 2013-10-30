pipumpkin
=========
This is a python program which accepts text-to-speech requests sent to an e-mail account and plays them out using espeak/pyttsx.
It is planned to be placed inside a pumpkin for office use only. Enjoy!

Make it yourself
================
You'll need:
* A Raspberry Pi
* A speaker system. Battery or USB-powered speakers can be embedded more easily!
* A gmail account with one folder to be used as a "speech queue"

Set-up
======
* Check-out this repository on the pi filesystem
* Create a folder (label) in your gmail account.
* Install the requirements; see helper scripts in 'setup'
* Create a json file with your mail server account details

/etc/pipumpkin-email-config
---------------------------
Example contents:
.code-block:
  {
    "user":"your-name@gmail.com",
    "password":"your-password",
    "imap-server":"imap.gmail.com",
    "imap-mailbox": "pipumpkin",
    "smtp-server": "smtp.gmail.com"
  }


