#!/usr/bin/python

import pygame
import sys
import time
import os
import json
import urllib2
import evdev
from threading import Thread
import Queue
import logging
from threading import Lock

TOUCHSCREEN_DEV="/dev/input/event0"


IMAGES_PATH="/home/pi/solarclock_images/"
EARTHIMAGE_PATH=os.path.join(IMAGES_PATH, "earth.png")
MOONIMAGE_PATH=os.path.join(IMAGES_PATH, "moon.png")
MARSIMAGE_PATH=os.path.join(IMAGES_PATH, "mars.png")

# TODO this should all be converted into a dictionary 
IMAGES_ENABLED=[EARTHIMAGE_PATH, MOONIMAGE_PATH, MARSIMAGE_PATH]

ROTATION_SPEED=30 #in seconds
ROTATION_INTERVAL=0.1 #in seconds
CHANGESCREEN_RATELIMIT=0.2 # in seconds


ISS_MARKER_FILE="/usr/share/xplanet/markers/iss"
ISS_MARKER_ICON="iss.png"
ISS_LOCATION_URL="http://api.open-notify.org/iss-now.json"
# {"message": "success", "timestamp": 1492455258, "iss_position": {"longitude": "-118.6624", "latitude": "33.5182"}}

logging.basicConfig(filename='main.log', level=logging.DEBUG, format="[%(threadName)s]: %(message)s")
pygame.init()

def refresh_images():
	logging.info("Refreshing images.")
	earth_cmd="xplanet -projection rectangular -geometry 800x480  -config overlay_clouds -output "+ EARTHIMAGE_PATH +" -verbosity 10 -num_times 1"
	os.system(earth_cmd)
	moon_cmd="xplanet -config moon_orbit -geometry 800x480  -radius 35 -num_times 1 -output "+MOONIMAGE_PATH
	os.system(moon_cmd)
	mars_cmd="xplanet -body mars -geometry 800x480 -projection rectangular -num_times 1 -marker_file mars -longitude 20 -output "+MARSIMAGE_PATH
	os.system(mars_cmd)
	logging.info("Image refreshes complete.")


def build_marker_file():
	marker_string = " image=" + ISS_MARKER_ICON
	try:
		r = urllib2.urlopen(ISS_LOCATION_URL)
		data = json.loads(r.read())
	except:
		print "Failed to contact API for ISS location."
		return False
	if data['message'] != "success":
		logging.warning("API for ISS Location reports unsuccessful: " + str(data))
		return False
	
	lat = str(data['iss_position']['latitude'])
	long = str(data['iss_position']['longitude'])

	marker_string = lat + " " + long + " " + marker_string
	logging.info("Updating marker string file with " + str(marker_string))

	fd = open(ISS_MARKER_FILE, 'w')
	fd.write(marker_string)
	fd.close()
	

def touchscreen_monitor():
	logging.info("Touchscreen monitor thread reporting for duty.")
	tf = evdev.InputDevice(TOUCHSCREEN_DEV)
	for event in tf.read_loop():
		logging.info("From touch screen: " + str(evdev.categorize(event)))
		mqueue.put(event)

def image_refresher():
	logging.info("Refresher thread reporting for duty.")
	while 1: 
		# TODO: this can take a while, and unfortunately it has 
		# to be done under a lock shared with the actual updating
		# of the screen; because if they collide, the main 
		# program crashes.  There are better ways to handle this scenario; 
		# this one was just easiest. 
		logging.info("Beginning image update.")
		screenLock.acquire()	
		build_marker_file()
		refresh_images()
		screenLock.release()
		logging.info("Image update complete.")
		time.sleep(60)

mqueue = Queue.Queue()
tmt = Thread(target=touchscreen_monitor)
tmt.start()

irt = Thread(target=image_refresher)
irt.start()

screenLock = Lock() 

logging.info("Spawned touchscreen monitor thread.")

lastChangeTime = 0

size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
black = 0, 0, 0
screen = pygame.display.set_mode(size)
pygame.mouse.set_visible(False)

while [ 1 ]:

	for i in IMAGES_ENABLED:
		logging.info("Displaying" + str(i))

		# when this lock collides with the refresher taking the lock, it'll
		# stall for a few seconds.  Womp womp. Probably TODO the refresher
		# should use temp files and then move them into place, so that it 
		# takes an unperceptible amount of time.
		screenLock.acquire()
		ball = pygame.image.load(i)
		ballrect = ball.get_rect()

		screen.fill(black)
		screen.blit(ball, ballrect)
		pygame.display.flip()
		screenLock.release()

		logging.info("Updated display. Beginning sleep loop.")

		# wait for the specified time, or for input from the touch screen
		time_slept=0
		nextPane = False
		while time_slept < ROTATION_SPEED:
			time.sleep(ROTATION_INTERVAL)
			time_slept+=ROTATION_INTERVAL
#			logging.debug("Slept for " + str(ROTATION_INTERVAL))

			# check if there's some action on the touchscreen
			while mqueue.qsize() > 0: 
				logging.info("Found "+str(mqueue.qsize()) +" touchscreen events in the queue.")
				# something's happened.  Empty the queue and move on.
				# TODO: a better way to do this is to look for press/unpress events, rather than 
				# any event at all, and then the CHANGESCREEN_RATELIMIT is probably no longer
				# required, and the user experience would be improved. 
				logging.debug("Got " + str(mqueue.get(False)))
				nextPane = True
			logging.debug("Queue is empty.")
			if nextPane: 
				if CHANGESCREEN_RATELIMIT > (time.time() - lastChangeTime):
					logging.warning("Trying to change too fast - refuse!")
					nextPane = False
				else:
					lastChangeTime=time.time()
					logging.info("Fastforward!")
					break
				

