import time
from datetime import datetime
def main():
   print "starting up!"
   with open("/tmp/touchme","a") as f:
      f.write(str(datetime.now()))
   time.sleep(10)
