import asyncio
import json
import requests
import time

from airtouch4pyapi import AirTouch, AirTouchStatus

EMONCMS_API_KEY = "YOUR EMONCMS API KEY"
EMONCMS_HEADERS = {"Authorization": f"Bearer {EMONCMS_API_KEY}"}
EMONCMS_SERVER_IP = "EMONCMS IP"
INTERVAL = 5
AIRTOUCH_IP = "AIRTOUCH4 IP"
PUSHOVER_TOKEN = "YOUR TOKEN"
PUSHOVER_USER_KEY = "YOUR KEY"


MODE_MAP = {
	"Cool": 2,
	"Fan": 0,
	"Dry": 7,
	"Heat": 1,
	"AutoCool": 22,
	"AutoHeat": 11
}

# EMONCMS FEED ID LIST BELOW. ADJUST TO SUIT YOUR SETUP
AC_POWER_STATE_FEED_ID = 458

AC_MODE_PRE_SPIKE_FEED_ID = 514
AC_POWER_PRE_AWAY_FEED_ID = 515

AC_MODE_KNOWN_SPIKE_FEED_ID = 509
AC_POWER_KNOWN_AWAY_FEED_ID = 510

PRICE_SPIKE_FEED_ID = 217
AC_AUTOMATION_FEED_ID = 511
AWAY_MODE_FEED_ID = 513

FAN_MODE = "Fan"

session = requests.Session()

def map_mode(mode, reverse=False):
	if reverse:
		for key, value in MODE_MAP.items():
			if value == mode:
				return key
	else:
		return MODE_MAP.get(mode)

def post_to_emoncms(node_name, data):
	url = f"http://{EMONCMS_SERVER_IP}/input/post.json?node={node_name}&fulljson={data}"
	response = session.post(url, headers=EMONCMS_HEADERS)
	response.raise_for_status()
	if response.status_code != 200:
		print(f"Error posting data to EmonCMS: {response.content}")

def get_feed_value(feed_id):
	url = f"http://{EMONCMS_SERVER_IP}/feed/value.json?id={feed_id}"
	response = session.get(url, headers=EMONCMS_HEADERS)
	response.raise_for_status()
	return int(response.text)

def get_state_changes():
	spike1 = get_feed_value(PRICE_SPIKE_FEED_ID)
	spike2 = get_feed_value(AC_MODE_KNOWN_SPIKE_FEED_ID)
	
	away1 = get_feed_value(AWAY_MODE_FEED_ID)
	away2 = get_feed_value(AC_POWER_KNOWN_AWAY_FEED_ID)
	if spike1 != spike2:
		return "spike"
	if away1 != away2:
		return "away"
	return False

def away_mode():
	if get_feed_value(AWAY_MODE_FEED_ID) == 1:
		return True
	return False

def send_notification(str):
    url = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": "Airtouch Automation",
		"message": {str}
    }
    #response = requests.post(url, data=data)
    response = session.post(url, data=data)
    response.raise_for_status()
    if response.status_code != 200:
        print(f"Error sending notification: {response.content}")
        
def set_known_modes():
	post_to_emoncms("AUTOMATION", json.dumps({"ac-mode-known-spike": get_feed_value(PRICE_SPIKE_FEED_ID)}))
	post_to_emoncms("AUTOMATION", json.dumps({"ac-power-known-away": get_feed_value(AWAY_MODE_FEED_ID)}))

async def update_airtouch_mode(mode):
	#ac = at.GetAcs()[0]
	at = AirTouch(AIRTOUCH_IP)
	await at.UpdateInfo()
	if at.Status != AirTouchStatus.OK:
		print("Got an error updating info. Exiting")
		return
	await at.SetCoolingModeForAc(0, mode)
	await at.UpdateInfo()
	
async def set_airtouch_power(power):
	at = AirTouch(AIRTOUCH_IP)
	if power == "on":
		#ac = at.GetAcs()[0]
		await at.UpdateInfo()
		if at.Status != AirTouchStatus.OK:
			print("Got an error updating info. Exiting")
			return
		await at.TurnAcOn(0)
		await at.UpdateInfo()
	if power == "off":
		#ac = at.GetAcs()[0]
		await at.UpdateInfo()
		if at.Status != AirTouchStatus.OK:
			print("Got an error updating info. Exiting")
			return
		await at.TurnAcOff(0)
		await at.UpdateInfo()

async def get_airtouch_power():
	at = AirTouch(AIRTOUCH_IP)
	await at.UpdateInfo()
	if at.Status != AirTouchStatus.OK:
		print("Got an error updating info. Exiting")
		return
	ac = at.GetAcs()[0]
	ac_power = 0 if ac.PowerState == "Off" else 1
	return ac_power


async def get_airtouch_currentmode():
	at = AirTouch(AIRTOUCH_IP)
	await at.UpdateInfo()
	if at.Status != AirTouchStatus.OK:
		print("Got an error updating info. Exiting")
		return
	ac = at.GetAcs()[0]
	current_mode = ac.AcMode
	return current_mode
	

async def update_info_and_display():
	try:
		state_changes = get_state_changes()
		automation_feed_value = get_feed_value(AC_AUTOMATION_FEED_ID)
		if automation_feed_value == 0:
			print("Aircon automation disabled. Exiting.")
			return

		pre_spike_mode_str = str(map_mode(get_feed_value(AC_MODE_PRE_SPIKE_FEED_ID), reverse=True))
		spike_value = get_feed_value(PRICE_SPIKE_FEED_ID)
	
		if away_mode() == True:
			#if get_feed_value(AC_POWER_STATE_FEED_ID) == 1:
			if await get_airtouch_power() == 1:
				post_to_emoncms("AUTOMATION", json.dumps({"ac-power-pre-away": 1}))
				print(f"Away mode is active. turning off AC")
				send_notification("Away mode is active. turning off AC")
				await set_airtouch_power("off")
				set_known_modes()
				return

		state_changes = get_state_changes()

		if state_changes == "away":
			power_before_away = get_feed_value(AC_POWER_PRE_AWAY_FEED_ID)
			if power_before_away == 1:
				if await get_airtouch_power() != power_before_away:
					print(f"Away mode disabled. turning on AC")
					send_notification("Away mode disabled. turning on AC")
					await set_airtouch_power("on")

		if state_changes == "spike":
			# Spike state has changed, update the Airtouch mode
			current_mode = await get_airtouch_currentmode()
			if spike_value != 0 and current_mode != FAN_MODE:
				print("Spike detected. Switching to fan mode.")
				previous_mode = map_mode(current_mode)
				post_to_emoncms("AUTOMATION", json.dumps({"ac-mode-pre-spike": previous_mode}))
				send_notification("Spike detected. Switching to fan mode.")
				await update_airtouch_mode(FAN_MODE)
			elif spike_value == 0 and current_mode == FAN_MODE:
				print("Spike is over. Switching back to original mode.")
				send_notification("Spike is over. Switching back to original mode.")
				await update_airtouch_mode(pre_spike_mode_str)
								
		set_known_modes()
								
	except Exception as e:
		print(f"Error updating info: {e}")


async def main():
	print("Starting up...")
	await update_info_and_display()
	print("Running.")
	while True:
		await asyncio.sleep(INTERVAL)
		await update_info_and_display()

if __name__ == "__main__":
	asyncio.run(main())
