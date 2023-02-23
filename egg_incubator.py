from flask import Flask, render_template, request, jsonify
import time
import RPi.GPIO as GPIO
from threading import Thread
from pymongo import MongoClient
import pymongo
from datetime import datetime, timedelta
import json
import board
import adafruit_ahtx0
from statistics import mean, pstdev
import numpy as np

with open('config.json') as config_file:
    config = json.load(config_file)

start_date = datetime.strptime(config['start_date'], '%Y-%m-%d')

# Connect to MongoDB
uri = config['uri']
client = MongoClient(uri)
db = client[config['database']]
incubator = db[config['collection']]


app = Flask(__name__, static_folder='static')

# Set the sensor type (DHT22) and the GPIO pin number
i2c = board.I2C()
sensor = adafruit_ahtx0.AHTx0(i2c)

# Set the relay pin number
egg_turner_relay_pin = 17
heat_relay_pin = 18
humidifier_relay_pin = 27

# Set the interval for logging data and turning on the relay (in seconds)
log_interval = config['log_interval']
relay_interval = config['relay_interval']
roll_interval = config['roll_interval']
last_relay_on = config['last_relay_on']
temperature_relay_status = config['temperature_relay_status']
humidity_relay_status = config['humidity_relay_status']
day_in_cycle = config['day_in_cycle']


# Set the temperature and humidity thresholds
temperature_threshold = 100
humidity_threshold = 50

# Initialize the GPIO pins
GPIO.setmode(GPIO.BCM)
GPIO.setup(heat_relay_pin, GPIO.OUT)
GPIO.setup(humidifier_relay_pin, GPIO.OUT)
GPIO.setup(egg_turner_relay_pin, GPIO.OUT)

def read_sensor_data():
    # Read the humidity and temperature
    humidity, temperature = sensor.relative_humidity, sensor.temperature
    if humidity is not None and temperature is not None:
        temperature = (temperature * 9/5) + 32
        return round(temperature,1), round(humidity,1)
    else:
        print('Failed to read data from sensor')
        return None, None


def log_data(temperature, humidity, last_relay_on, temperature_relay_status, humidity_relay_status, day_in_cycle):
    # Get the most recent record from the database
    last_record = incubator.find_one(sort=[('_id', pymongo.DESCENDING)])

    # Check if a record has been stored within the log interval
    if last_record is None or (datetime.now() - datetime.strptime(last_record['Time'], '%m-%d-%Y %H:%M')).total_seconds() >= log_interval:
        # Create a data dictionary
        data = {
            'Time': time.strftime("%m-%d-%Y %H:%M"),
            'Temperature(F)': temperature,
            'Temperature Relay Status': temperature_relay_status,
            'Humidity(%)': humidity,
            'Humidity Relay Status': humidity_relay_status,
            'Last Egg Turn': last_relay_on.strftime("%m-%d-%Y %I:%M %P") if last_relay_on is not None else '',
            'Day in Egg Cycle': day_in_cycle
        }

        # Insert the data into the incubator collection
        incubator.insert_one(data)


def eggTurner():
    global last_relay_on
    global day_in_cycle
    current_time = datetime.now()
    if day_in_cycle < 18:
        if last_relay_on is None:
            last_relay_on = datetime.now()
        if GPIO.input(egg_turner_relay_pin) == 1:
            if current_time - last_relay_on >= timedelta(seconds=relay_interval):
                # Turn on the relay for 2 minutes
                GPIO.output(egg_turner_relay_pin, GPIO.LOW)
                last_relay_on = current_time
        elif GPIO.input(egg_turner_relay_pin) == 0:        
            if current_time - last_relay_on >= timedelta(seconds=roll_interval):
                GPIO.output(egg_turner_relay_pin, GPIO.HIGH)
    return last_relay_on


def control():
    global temperature_relay_status
    global humidity_relay_status
    temperature, humidity = read_sensor_data()

    if temperature < temperature_threshold - 1:
        # Turn on the heat source
        GPIO.output(heat_relay_pin, GPIO.LOW)
        if GPIO.input(heat_relay_pin) == 0:
            temperature_relay_status = "ON"
        else:
            print("HEAT GPIO not setting to low or ON")
    elif temperature > temperature_threshold:
        # Turn off the heat source
        GPIO.output(heat_relay_pin, GPIO.HIGH)
        if GPIO.input(heat_relay_pin) == 1: 
            temperature_relay_status = "OFF"
        else:
            print("HEAT GPIO not setting to High or OFF")
    else:
        # Do nothing
        pass

    if humidity < (humidity_threshold - 5):
        # Turn on the humidifier
        GPIO.output(humidifier_relay_pin, GPIO.LOW)
        if GPIO.input(humidifier_relay_pin) == 0:
            humidity_relay_status = "ON"
        else:
            print("HUMIDITY GPIO not setting to low or ON")
    else:
        # Turn off the humidifier
        GPIO.output(humidifier_relay_pin, GPIO.HIGH)
        if GPIO.input(humidifier_relay_pin) == 1:
            humidity_relay_status = "OFF"
        else:
            print("HUMIDITY GPIO not setting to HIGH or OFF")


def day():
    global humidity_threshold
    current_date = datetime.now()
    total_days = 21
    day_in_cycle = (current_date - start_date).days % total_days
    if day_in_cycle >= 18:
        humidity_threshold = 75
    return day_in_cycle


def lock_down_and_hatch():
    lock_down_date = start_date + timedelta(days=18)
    hatch_date = start_date + timedelta(days=21)
    return lock_down_date,hatch_date


def update_config(variable, value):
    with open("config.json", "r") as config_file:
        config = json.load(config_file)
        config[variable] = value
    with open("config.json", "w") as config_file:
        json.dump(config, config_file)


def clear_database():
    incubator.drop()


def read_and_log_data():
    global last_relay_on
    global day_in_cycle

    try:
        while True:
            day_in_cycle = day()
            control()
            last_relay_on = eggTurner()
            temperature, humidity = read_sensor_data()
            log_data(temperature, humidity, last_relay_on, temperature_relay_status, humidity_relay_status, day_in_cycle)
            time.sleep(20)
            
    except KeyboardInterrupt:
        pass
    finally:
        # Clean up the GPIO pins
        GPIO.cleanup()
        # Close the MongoDB connection
        client.close()

def get_egg_cycle_statistics(historical_data):
    egg_cycle_dict = {}
    for data in historical_data:
        day = data['Day in Egg Cycle']
        temperature = data['Temperature(F)']
        humidity = data['Humidity(%)']
        if day in egg_cycle_dict:
            egg_cycle_dict[day]['temperature'].append(temperature)
            egg_cycle_dict[day]['humidity'].append(humidity)
        else:
            egg_cycle_dict[day] = {
                'temperature': [temperature],
                'humidity': [humidity],
            }
    
    egg_cycle_statistics = []
    for day, values in egg_cycle_dict.items():
        avg_temp = np.mean(values['temperature'])
        std_temp = np.std(values['temperature'])
        avg_hum = np.mean(values['humidity'])
        std_hum = np.std(values['humidity'])
        egg_cycle_statistics.append({
            'Day in Egg Cycle': day,
            'Average Temperature (F)': round(avg_temp, 2),
            'Temperature Standard Deviation': round(std_temp, 2),
            'Average Humidity (%)': round(avg_hum, 2),
            'Humidity Standard Deviation': round(std_hum, 2),
        })
        
    egg_cycle_statistics.sort(key=lambda x: x['Day in Egg Cycle'], reverse=True)
    return egg_cycle_statistics


@app.route("/")
def index():
    day_in_cycle = day()
    lock_down_date,hatch_date = lock_down_and_hatch()
    temperature, humidity = read_sensor_data()
    last_relay_on = eggTurner()
    last_relay_on = last_relay_on.strftime("%m-%d-%Y %I:%M %P") if last_relay_on is not None else ''
    cursor = incubator.find().limit(48).sort("Time", -1)
    historical_data = []
    
    for data in cursor:
        historical_data.append({
            'Time': data['Time'],
            'Temperature(F)': data['Temperature(F)'],
            'Temperature Relay Status': data['Temperature Relay Status'],
            'Humidity(%)': data['Humidity(%)'],
            'Humidity Relay Status': data['Humidity Relay Status'],
            'Last Egg Turn': data['Last Egg Turn'],
            'Day in Egg Cycle': data['Day in Egg Cycle']
        })
    egg_cycle_data = get_egg_cycle_statistics(historical_data)
    data = {
        'log_interval': log_interval,
        'relay_interval': relay_interval,
        'roll_interval': roll_interval,
        'temperature_threshold': temperature_threshold,
        'humidity_threshold': humidity_threshold,
        'historical_data': historical_data,
        'temperature': temperature,
        'humidity': humidity,
        'last_relay_on': last_relay_on,
        'temperature_relay_status': temperature_relay_status,
        'humidity_relay_status': humidity_relay_status,
        'day_in_cycle': day_in_cycle,
        'start_date': start_date.strftime("%m-%d-%Y"),
        'lock_down_date': lock_down_date.strftime("%m-%d-%Y"),
        'hatch_date': hatch_date.strftime("%m-%d-%Y"),
        'egg_cycle_data': egg_cycle_data,

    }
    return render_template('index.html', data=data)



@app.route('/update_settings', methods=['POST'])
def update_settings():
    global temperature_threshold
    global humidity_threshold
    global log_interval
    global relay_interval
    global roll_interval
    global start_date
    data = request.get_json()
    variable = data['variable']
    value = data['value']
    if variable == 'temperature_threshold':
        temperature_threshold = int(value)
    elif variable == 'humidity_threshold':
        humidity_threshold = int(value)
    elif variable == 'log_interval':
        log_interval = int(value) * 60
    elif variable == 'relay_interval':
        relay_interval = int(value) * 60 * 60
    elif variable == 'roll_interval':
        roll_interval = int(value) * 60
    elif variable == 'start_date':
        date = datetime.strptime(value, '%m/%d/%Y')
        start_date = datetime(date.year, date.month, date.day)
        formatted_date = date.strftime('%Y-%m-%d')
        update_config('start_date', formatted_date)
        clear_database()
    return jsonify({'status': 'success'})


if __name__ == "__main__":
    thread = Thread(target=read_and_log_data)
    thread.start()
    app.run(debug=True, host='0.0.0.0')