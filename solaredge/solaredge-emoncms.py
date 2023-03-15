#!/usr/bin/python3

import json
import asyncio
import solaredge_modbus
import aiohttp
from datetime import datetime

##################################################################################
HEALTHCHECKS_IO_URL = "YOUR-HEALCHECK-URL"

INTERVAL = 0 #SECONDS

LEADER_HOST = "localhost"   # IP ADDRESS OF FQDN OF THE INVERTER
LEADER_PORT = 9000          # TCP MODBUS PORT WITHIN THE INVERTER

PHASE_COLOUR = "RED"        # THIS CHANGES THE NODE NAME FOR POSTING INTO EMONCMS
LEADER_ENABLED = 1          # ENABLE TO READ DATA FROM THE INVERTER
LEADER_STORAGE_ENABLED = 0  # ENABLE TO READ STORAGE DATA FROM INVERTER
METER_ENABLED = 1           # ENABLE TO READ METER DATA (IF INSTALLED)
BATTERY1_ENABLED = 0        # ENABLE TO READ DATA FROM BATTERY 1
BATTERY2_ENABLED = 0        # ENABLE TO READ DATA FROM BATTERY 2

EMONCMS_API_KEY = "YOUR-EMONCMS-API-KEY"
EMONCMS_HEADERS = {"Authorization": f"Bearer {EMONCMS_API_KEY}"}
EMONCMS_SERVER_IP = "YOUR-EMONCMS-IP-OR-FQDN"

##################################################################################

async def health_check(status):
	url = f"{HEALTHCHECKS_IO_URL}"
	payload = {
		"status": {status},
		}
	async with aiohttp.ClientSession() as session:
		async with session.post(url, data=payload) as response:
			response.raise_for_status()
			if response.status != 200:
				print("Error sending health check ping to healthchecks.io")

async def get_device_data(data, type):
	master = solaredge_modbus.Inverter(host=LEADER_HOST, port=LEADER_PORT, retries=3, timeout=5, unit=1)
	if type == "leader":
		data = master.read_all()
		if len(data) < 52:
			print(f"Incomplete data for LEADER")
			return
		return data
	if type == "storage":
		data = solaredge_modbus.StorageInverter(parent=master).read_all()
		if len(data) < 12:
			print(f"Incomplete data for STORAGE")
			return
		return data
	if type == "meter":
		data = solaredge_modbus.Meter(parent=master, offset=0).read_all()
		if len(data) < 79:
			print(f"Incomplete data for METER")
			return
		return data
	if type == "battery1":
		await asyncio.sleep(0.2)
		data = master.batteries()["Battery1"].read_all()
		if len(data) < 23:
			print(f"Incomplete data for BATTERY1")
			return
		return data
	if type == "battery2":
		await asyncio.sleep(0.2)
		data = master.batteries()["Battery2"].read_all()
		if len(data) < 23:
			print(f"Incomplete data for BATTERY1")
			return
		return data
	else:
		return data.read_all()

# Device configurations
devices = {
	"LEADER": {
		"enabled": LEADER_ENABLED,
		"storage": LEADER_STORAGE_ENABLED,
		"read_storage": 1,
		"node_name": f"{PHASE_COLOUR}-INVERTER",
		"data_source": "leader",
		"storage_source": "storage"
	},
	"METER": {
		"enabled": METER_ENABLED,
		"read_storage": 0,
		"node_name": f"{PHASE_COLOUR}-METER",
		"data_source": "meter"
	},
	"BATTERY1": {
		"enabled": BATTERY1_ENABLED,
		"read_storage": 0,
		"node_name": f"{PHASE_COLOUR}-BATTERY1",
		"data_source": "battery1"
	},
	"BATTERY2": {
		"enabled": BATTERY2_ENABLED,
		"read_storage": 0,
		"node_name": f"{PHASE_COLOUR}-BATTERY2",
		"data_source": "battery2"
	}
}

async def process_device_data(device_name, device_config, session):
	task = asyncio.create_task(get_device_data(0, device_config["data_source"]))
	values = await task
	#print(f"{device_config['data_source']} {datetime.now()}")
	processed_data = {}
	for k, v in values.items():
		if (isinstance(v, int) or isinstance(v, float)) and "_scale" not in k:
			k_split = k.split("_")
			scale = 0
			if f"{k_split[len(k_split) - 1]}_scale" in values:
				scale = values[f"{k_split[len(k_split) - 1]}_scale"]
			elif f"{k}_scale" in values:
				scale = values[f"{k}_scale"]
			processed_data.update({k: float(v * (10 ** scale))})
			if device_config["data_source"] == "meter":
				if (isinstance(v, int) or isinstance(v, float)):
					if k == "l1_power" or k == "l2_power" or k == "l3_power":
						processed_data.update({k: float(v * (-1))})
	if device_config["read_storage"]:
		if device_config["storage"]:
			storagetask = asyncio.create_task(get_device_data(0, device_config["storage_source"]))
			storagevalues = await storagetask
			processed_data.update(storagevalues)
	node_name = device_config["node_name"]
	data = json.dumps(processed_data)
	url = f"http://{EMONCMS_SERVER_IP}/input/post.json?node={node_name}&fulljson={data}"
	async with session.post(url, headers=EMONCMS_HEADERS) as response:
		response.raise_for_status()
		if response.status != 200:
			print(f"Error posting data to EmonCMS: {response.content}")

async def update_info_and_display():
	async with aiohttp.ClientSession() as session:
		tasks = []
		for device_name, device_config in devices.items():
			if device_config["enabled"]:
				task = asyncio.create_task(process_device_data(device_name, device_config, session))
				tasks.append(task)
		try:
			await asyncio.gather(*tasks)
			await health_check("success")
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
