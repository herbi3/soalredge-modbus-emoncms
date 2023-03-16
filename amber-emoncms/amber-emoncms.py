#!/usr/bin/python3

import time
import datetime
import requests
import json

HEALTH_CHECK_URL = "YOUR HEALTHCHECK URL"
EMONCMS_HOST = "http:// - YOUR EMONCMS IP RO FQDN"
INTERVAL = 275 #SECONDS
SITE_ID = "YOUR AMBER ENERGY SITE_ID"
AMBER_PRICE_URL = f"https://api.amber.com.au/v1/sites/{SITE_ID}/prices/current"
AMBER_JSON_HEADERS = {"accept": "application/json"}
AMBER_HEADERS = {"Authorization": "Bearer YOUR AMBER API-KEY"}
NODE_NAME = "PRICES"
EMONCMS_API_KEY = 'YOUR EMONCMS API KEY'
EMONCMS_HEADERS = {"Authorization": f"Bearer {EMONCMS_API_KEY}"}

session = requests.Session()

def clear_emoncms_data():
	url_clean = f"{EMONCMS_HOST}/emoncms/input/clean"
	response = session.post(url_clean, headers=EMONCMS_HEADERS, verify=False)
	response.raise_for_status()
	print("Cleared emonCMS data")

def post_emoncms_data():
	response = session.get(AMBER_PRICE_URL, headers=AMBER_HEADERS, verify=True)
	response.raise_for_status()
	data = response.json()
	general = data[0]
	feedin = data[1]
	spike_status = 1 if general['spikeStatus'] != "none" else 0
	data = {
		"SPIKE-STATUS": spike_status,
		"RENEWABLES": feedin['renewables'],
		"AMBER-SOLAR": feedin['perKwh'] * -1,
		"AMBER-IMPORT": general['perKwh'],
		"ORIGIN-SOLAR": 5,
		"ORIGIN-IMPORT": 25.82,
	}
	data = json.dumps(data, indent=4, separators=(',', ':'))
	url = f"{EMONCMS_HOST}/input/post?node={NODE_NAME}&fulljson={data}"
	response = session.post(url, headers=EMONCMS_HEADERS, verify=False)
	response.raise_for_status()

while True:
	try:
		start_time = time.time()
		post_emoncms_data()

		if datetime.datetime.now().minute % 10 == 0:
			clear_emoncms_data()

		if session.head(HEALTH_CHECK_URL, timeout=1).status_code != 200:
			print("Health check connection failure")
			continue

		# Calculate and print the time it took to run the loop
		end_time = time.time()
#		print(f"Loop finished in {end_time - start_time:.3f} seconds")
		time.sleep(INTERVAL)

	except requests.exceptions.Timeout as e:
		print("Connection Timeout Exception")
		continue

	except requests.exceptions.HTTPError as e:
		print(f"HTTP Error: {e.response.status_code} - {e.response.reason}")
		time.sleep(INTERVAL)
		continue

	except requests.exceptions.RequestException as e:
		print("Request Exception:", e)
		time.sleep(INTERVAL)
		continue

	except Exception as e:
		print("Exception:", e)
		time.sleep(INTERVAL)
		continue
