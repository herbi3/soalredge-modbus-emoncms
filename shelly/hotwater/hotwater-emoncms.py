import asyncio
import time
import requests
import json

HEALTHCHECK_URL = "YOUR HEALTHCHECK URL"
EMONCMS_BASE_URL = "http:// YOUR EMONCMS OR IP"
INTERVAL = 2
EMONCMS_API_KEY = "YOUR EMONCMS API-KEY"
EMONCMS_URL = f"{EMONCMS_BASE_URL}/input/post?"
EMONCMS_HEADERS = {"Authorization": f"Bearer {EMONCMS_API_KEY}"}

SHELLEY_DEVICE = "http://10.0.2.36/" #REPLACE WITH YOUR SHELLY DEVICE IP ADDRESS
SHELLEY_SETTINGS = "settings"
SHELLEY_STATUS = "status"

session = requests.Session()

def check_healthcheck():
	response = session.post(HEALTHCHECK_URL, timeout=1)
	response.raise_for_status()
	if response.status_code != 200:
		print("Health check connection failure")
		return False
	return True

def post_to_emoncms(device_data, device_name):
	relay = int(device_data['relays'][0]['ison'])
	power = float(device_data['meters'][0]['power'])
	temperature = float(device_data['temperature'])
	rssi = int(device_data['wifi_sta']['rssi'])

	api_data = {"relay": relay, "power": power, "temperature": temperature, "rssi": rssi}
	json_data = json.dumps(api_data, separators=(',', ':'))

	response = session.post(EMONCMS_URL + f"&node={device_name}&fulljson={json_data}", headers=EMONCMS_HEADERS, timeout=2)
	response.raise_for_status()
	if response.status_code != 200:
		print(f"Error posting data to EmonCMS: {response.content}")

def get_device_info(str):
	if str == "data":
		response = session.get(SHELLEY_DEVICE + SHELLEY_STATUS, timeout=2).json()
	if str == "name":
		response = session.get(SHELLEY_DEVICE + SHELLEY_SETTINGS, timeout=2).json()
		response = response['name']
	return response

async def update_info_and_display():
	try:
		start_time = time.time()

		# Get the device name
		device_name = get_device_info("name")

		# Get the device data
		device_data = get_device_info("data")

		# Post the data to emoncms
		post_to_emoncms(device_data, device_name)

		# Check the healthcheck
		if not check_healthcheck():
			return

		# Calculate the time taken to run the code
		time_taken = time.time() - start_time
		#print(f"Time taken: {time_taken:.2f} seconds")

	except requests.exceptions.Timeout:
		print("Connection Failure Exception")
		exit()

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
