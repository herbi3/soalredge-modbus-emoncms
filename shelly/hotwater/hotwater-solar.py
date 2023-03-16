import asyncio
import json
import requests
import time
import datetime

EMONCMS_API_KEY = "YOUR EMONCMS IP ADDRESS"
EMONCMS_HEADERS = {"Authorization": f"Bearer {EMONCMS_API_KEY}"}
EMONCMS_SERVER_IP = "EMONCMS IP ADDRESS"
SHELLY_BASE_URL = "http://10.0.2.36/" # YOUR SHELLY DEVICE IP ADDRESS
INTERVAL = 60 #SECONDS
BATTERY_FEED_ID = [350, 362, 342] #RED 342
GRID_FEED_ID = 446
AWAY_MODE_FEED_ID = 513
SOLAR_PRICE_FEED_ID = 213
HOT_WATER_AUTOMATION_FEED_ID = 512
HOT_WATER_TODAY = 233
HOT_WATER_CONSUMPTION = 3600 #WATTS
HEALTHCHECK_ID = "YOUR HEALTHCHECK ID"

session = requests.Session()

def get_feed_value(feed_id):
	#url = f"{EMONCMS_BASE_URL}{feed_id}"
	url = f"http://{EMONCMS_SERVER_IP}/feed/value.json?id={feed_id}"
	response = session.post(url, headers=EMONCMS_HEADERS)
	response.raise_for_status()
	if response.status_code != 200:
		print(f"Error getting data from EmonCMS: {response.content}")
	return float(response.json())

def get_grid_battery_status(x):
	battery_status = sum([get_feed_value(battery_id) for battery_id in BATTERY_FEED_ID]) * -1
	grid_status = get_feed_value(GRID_FEED_ID)
	combined = grid_status + battery_status
	if x != 0:
		print(f"Grid status: {grid_status}, Battery status: {battery_status}, Total Status: {combined}")
	return grid_status + battery_status

def get_battery_status():
	battery_status = sum([get_feed_value(battery_id) for battery_id in BATTERY_FEED_ID]) * -1
	# return "1" if discharging - return "0" if not discharging
	if battery_status > 0:
		battery_status = 1
	else:
		battery_status = 0
	print(f"Battery discharging: {battery_status}")
	return battery_status

def set_hot_water(is_hot_water_on):
	set_health_status()
	current_hot_water_status = get_hot_water_status(1)
	if current_hot_water_status == is_hot_water_on:
		print(f"Hot water already in desired state: {is_hot_water_on}")
		return
	hot_water_status = "on" if is_hot_water_on else "off"
	response = session.post(f"{SHELLY_BASE_URL}relay/0?turn={hot_water_status}")
	response.raise_for_status()
	print(f"Hot water turned {hot_water_status}")

def get_hot_water_status(x):
	response = session.get(f"{SHELLY_BASE_URL}status")
	status = response.json()['relays'][0]['ison']
	if x > 0:
		print(f"Hot water status: {status}")
	return status

def get_forced_status():
	force_on = 0
	if datetime.datetime.now().hour >= 13 and datetime.datetime.now().hour < 16:
		consumption_today = get_feed_value(HOT_WATER_TODAY)
		if consumption_today < 16:
			force_on = 1
	print(f"Forced Status: {force_on}")
	return force_on

def get_schedule_status():
	schedule = 1 if datetime.datetime.now().hour >= 8 and datetime.datetime.now().hour < 16 else 0
	return int(schedule)

def get_is_exporting():
	grid_battery_status = get_grid_battery_status(1)
	if get_hot_water_status(0) != 1:
		is_exporting = grid_battery_status + HOT_WATER_CONSUMPTION < 0
	else:
		is_exporting =  grid_battery_status < 0
	return is_exporting

def set_health_status():
	url = f"https://hc-ping.com/{HEALTHCHECK_ID}"
	payload = {
		"status": "healthy",
		}
	response = session.post(url, data=payload)
	response.raise_for_status()
	if response.status_code == 200:
		print("Healthcheck status updated successfully!")
	else:
		print("Error updating healthcheck status:", response.text)

async def update_info_and_display():
	try:
		automation_feed_value = get_feed_value(HOT_WATER_AUTOMATION_FEED_ID)
		print(f"Automation swich status: {automation_feed_value}")
		if automation_feed_value == 0:
			set_hot_water(True)
			return

		if get_schedule_status() != 1:
			set_hot_water(False)
			return

		away_mode_status = get_feed_value(AWAY_MODE_FEED_ID)
		print(f"Away mode status: {away_mode_status}")
		solar_price = get_feed_value(SOLAR_PRICE_FEED_ID)
		grid_battery_status = get_grid_battery_status(0)
		#battery_status = get_battery_status()
		battery_status = 0
		forced_status = get_forced_status()
		now = datetime.datetime.now().time()
		is_exporting = get_is_exporting()
		if (automation_feed_value == 0 or (is_exporting or solar_price < 0 or forced_status == 1)) and not (battery_status or away_mode_status):
			set_hot_water(True)
		else:
			set_hot_water(False)
			
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
