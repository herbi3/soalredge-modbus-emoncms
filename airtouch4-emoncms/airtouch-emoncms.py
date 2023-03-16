import asyncio
import json
import requests
import time

from airtouch4pyapi import AirTouch, AirTouchStatus

EMONCMS_API_KEY = "YOUR-EMONCMS-API-KEY"
EMONCMS_HEADERS = {"Authorization": f"Bearer {EMONCMS_API_KEY}"}
EMONCMS_SERVER_IP = "EMONCMS IP OR FQDN"
EMONCMS_UPDATE_INTERVAL = 60
AIRTOUCH_IP = "AIRTOUCH4-IP"
HEALTHCHECKS_IO_URL = "HEALTHCHECK-URL"

session = requests.Session()

FAN_SPEED_MAP = {
	"Auto": 0,
	"Low": 1,
	"Medium": 3,
	"High": 5
}

MODE_MAP = {
	"Cool": 2,
	"Fan": 0,
	"Dry": 7,
	"Heat": 1,
	"AutoCool": 22,
	"AutoHeat": 11
}

POWER_STATE_MAP = {
	"Off": 0,
	"On": 1,
	"Turbo": 2
}

def map_fan_speed(fan_speed):
	return FAN_SPEED_MAP.get(fan_speed)

def map_mode(mode):
	return MODE_MAP.get(mode)

def map_power_state(power_state):
	return POWER_STATE_MAP.get(power_state)

def post_to_emoncms(node_name, data):
	url = f"http://{EMONCMS_SERVER_IP}/input/post.json?node={node_name}&fulljson={data}"
	response = session.post(url, headers=EMONCMS_HEADERS)
	response.raise_for_status()
	if response.status_code != 200:
		print(f"Error posting data to EmonCMS: {response.content}")

def health_check(status):
	url = f"{HEALTHCHECKS_IO_URL}"
	payload = {
		"status": {status},
		}
	response = session.post(url, data=payload)
	response.raise_for_status()
	if response.status_code != 200:
		print("Error sending health check ping to healthchecks.io")

async def update_info_and_display(ip):
	at = AirTouch(ip)
	await at.UpdateInfo()
	if at.Status != AirTouchStatus.OK:
		print("Got an error updating info. Exiting")
		return
	acs = at.GetAcs()
	groups = at.GetGroups()

	data = {"acs": [], "groups": []}
	for ac in acs:
		fan_speed = map_fan_speed(ac.AcFanSpeed)
		power_state = map_power_state(ac.PowerState)
		mode = map_mode(ac.AcMode)
		ac_data = {
			"AcNumber": ac.AcNumber,
			"PowerState": power_state,
			"TargetTemp": float(ac.AcTargetSetpoint),
			"CurrentTemp": float(ac.Temperature),
			"Mode": mode,
			"FanSpeed": fan_speed,
			"StartGroup": float(ac.StartGroupNumber),
			"GroupCount": float(ac.GroupCount),
			"Delta": float(ac.Temperature)-float(ac.AcTargetSetpoint)
		}
		data["acs"].append(ac_data)
		ac_node_name = f"AC_{ac_data['AcNumber']}"
		post_to_emoncms(ac_node_name, json.dumps(ac_data))
		for group in groups:
			if group.BelongsToAc == ac.AcNumber:
				power_state = map_power_state(group.PowerState)
				group_data = {
					"GroupNumber": int(group.GroupNumber),
					"PowerState": power_state,
					"ControlMethod": 0 if group.ControlMethod == "TemperatureControl" else 1,
					"OpenPercentage": float(group.OpenPercentage),
					"CurrentTemp": float(group.Temperature),
					"TargetTemp": float(group.TargetSetpoint),
					"LowBattery": float(group.BatteryLow),
					"SpillActive": float(group.Spill),
					"Delta": float(group.Temperature)-float(group.TargetSetpoint),
				}
				if power_state != 0:
					active_delta = float(group.Temperature) - float(group.TargetSetpoint)
					group_data.update({"ActiveDelta": active_delta})
				data["groups"].append(group_data)
				group_node_name = f"AC_{ac_data['AcNumber']}_Zone_{group_data['GroupNumber']}"
				post_to_emoncms(group_node_name, json.dumps(group_data))

	data_str = json.dumps(data)
	post_to_emoncms("AirTouchData", data_str)
	health_check("success")

async def main():
	while True:
		try:
			await update_info_and_display(AIRTOUCH_IP)
			print(f"Data posted to EmonCMS at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
		except Exception as e:
			print(f"Exception: {str(e)}")
			health_check("fail")
		await asyncio.sleep(EMONCMS_UPDATE_INTERVAL)

if __name__ == "__main__":
	asyncio.run(main())
