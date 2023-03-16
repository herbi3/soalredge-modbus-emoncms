from influxdb import InfluxDBClient
from datetime import datetime, timedelta
import time
import calendar
import asyncio
import requests
import json
import aiohttp
#import datetime

INTERVAL = 30 * 60
EMONCMS_API_KEY = "YOUR EMONCMS API KEY"
EMONCMS_HEADERS = {"Authorization": f"Bearer {EMONCMS_API_KEY}"}
EMONCMS_SERVER_IP = "YOUR EMONCMS IP"

PREVIOUS_MONTHS_FEED_ID = 529

DAILY_SUPPLY_CHARGE = "101" #CENTS
DEMAND_CHARGE = "342" #CENTS
AMBER_MONTHLY_CHARGE = "1500" #CENTS

def get_max_difference(start_time_ms, end_time_ms):
	# Connect to InfluxDB
	client = InfluxDBClient(host='localhost', port=8086, username='YOUR INFLUXDB ADMIN USERNAME', password='YOUR INFLUXDB PASSWORD', database='telegraf')

	# Construct the query
	query = f"SELECT MAX(*) FROM (SELECT difference(last(\"value\")) FROM \"mqtt_consumer\" WHERE (\"topic\" = 'SOLAREDGE/NET-DEMAND-IMPORT-KWH') AND time >= {start_time_ms}ms AND time <= {end_time_ms}ms GROUP BY time(30m) fill(null)), \"topic\" fill(previous)"

	try:
		# Query InfluxDB
		result = client.query(query)
		result_value = list(result.get_points())[0]
		#value = float("{:.4f}".format(result_value['max_difference']))
		return float("{:.6f}".format(result_value['max_difference'])) * 2
	except IndexError:
		return 0
	except Exception as e:
		print(f"Error querying InfluxDB: {e}")
		return None

async def get_feed_value(feed_id):
    url = f"http://{EMONCMS_SERVER_IP}/feed/value.json?id={feed_id}"

    try:
        async with aiohttp.ClientSession(headers=EMONCMS_HEADERS) as session:
            async with session.post(url) as response:
                response.raise_for_status()
                return float(await response.text())
    except Exception as e:
        print(f"Error getting data from EmonCMS: {e}")
        return None


async def post_to_emoncms(node_name, subname, value):
	data = {subname: value}
	json_data = json.dumps(data, separators=(',', ':'))
	url = f"http://{EMONCMS_SERVER_IP}/input/post.json?node={node_name}&fulljson={json_data}"

	try:
		async with aiohttp.ClientSession(headers=EMONCMS_HEADERS) as session:
			async with session.post(url) as response:
				response.raise_for_status()
				#print(f"Posted {value} to {node_name} on EmonCMS")
	except Exception as e:
		print(f"Error posting data to EmonCMS: {e}")

def get_daily_cost():
    now = time.time()
    time_tuple = time.localtime(now)
    year = time_tuple.tm_year
    month = time_tuple.tm_mon
    days_in_month = calendar.monthrange(year, month)[1]
    daily_cost = int(AMBER_MONTHLY_CHARGE) / days_in_month
    return daily_cost

async def update_info_and_display():
	# Get the current time and dates for this month and last month
	now = datetime.now().replace(microsecond=0)
	last_month_end = now.replace(day=1) - timedelta(days=1)
	last_month_start = last_month_end.replace(day=1)
	this_month_start = now.replace(day=1)
	this_month_end = now

	# Check if it's the 1st of the month at midnight
	#if now.day == 1 and now.hour == 0 and now.minute == 0:

	# Convert the start and end dates for last month to milliseconds
	start_time_ms = int(last_month_start.timestamp() * 1000)
	end_time_ms = int(last_month_end.timestamp() * 1000)

	# Call the get_max_difference function for last month
	max_difference = get_max_difference(start_time_ms, end_time_ms)
	if max_difference > 0:
		if await get_feed_value(PREVIOUS_MONTHS_FEED_ID) != max_difference:
			await post_to_emoncms("MAX-30M-DEMAND", "previous-months", max_difference)
			await post_to_emoncms("MAX-30M-DEMAND", "previous-months-cost", max_difference)
			await post_to_emoncms("MAX-30M-DEMAND", "previous-months-cost", max_difference * float(DEMAND_CHARGE))
		else:
			print("No changes for last month")
	else:
		print("No data found for last month")

	# Convert the start and end dates for this month to milliseconds
	start_time_ms = int(this_month_start.timestamp() * 1000)
	end_time_ms = int(this_month_end.timestamp() * 1000)

	# Call the get_max_difference function for this month
	max_difference = get_max_difference(start_time_ms, end_time_ms)
	if max_difference == 0:
		print("No data found for this month")
	await post_to_emoncms("MAX-30M-DEMAND", "current-month", max_difference)
	await post_to_emoncms("MAX-30M-DEMAND", "demand-charge", float(DEMAND_CHARGE))
	await post_to_emoncms("MAX-30M-DEMAND", "daily-supply-charge", float(DAILY_SUPPLY_CHARGE))
	await post_to_emoncms("MAX-30M-DEMAND", "daily-monthly-charge", get_daily_cost())
	await post_to_emoncms("MAX-30M-DEMAND", "current-month-cost", max_difference * float(DEMAND_CHARGE))
	#else:
		#print("No data found for this month")

async def main():
	print("Starting up...")
	await update_info_and_display()
	print("Running.")
	while True:
		await asyncio.sleep(INTERVAL)
		await update_info_and_display()

if __name__ == "__main__":
	asyncio.run(main())

