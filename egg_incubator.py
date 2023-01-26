from flask import Flask, render_template,request, jsonify,redirect 
import time
import Adafruit_DHT
import RPi.GPIO as GPIO
from threading import Thread
from pymongo import MongoClient
import pymongo
from datetime import datetime, timedelta
import json

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
sensor = Adafruit_DHT.DHT22
pin = 4

# Set the relay pin number
egg_turner_relay_pin = 17
heat_relay_pin = 18
humidifier_relay_pin = 19

# Set the interval for logging data and turning on the relay (in seconds)
log_interval = config['log_interval']
relay_interval = config['relay_interval']
roll_interval = config['roll_interval']
last_relay_on = config['last_relay_on']
dataLogged = config['dataLogged']
eggPin = config['eggPin']
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
GPIO.setup(20, GPIO.OUT)
GPIO.output(20, GPIO.HIGH)





def read_sensor_data():
    # Read the humidity and temperature
    humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
    if humidity is not None and temperature is not None:
        temperature = (temperature * 9/5) + 32
        return round(temperature,1), round(humidity,1)
    else:
        print('Failed to read data from sensor')
        return None, None


def log_data(temperature, humidity, last_relay_on,temperature_relay_status,humidity_relay_status,day_in_cycle):
    # Create a data dictionary
    data = {
        'Time': time.strftime("%m-%d-%Y %H:%M"),
        'Temperature(F)': temperature,
        'Temperature Relay Status': temperature_relay_status,
        'Humidity(%)': humidity,
        'Humidity Relay Status': humidity_relay_status,
        'Last Egg Turn': last_relay_on.strftime("%m-%d-%Y %I:%M %P"),
        'Day in Egg Cycle' : day_in_cycle
    }
    # Insert the data into the incubator collection
    incubator.insert_one(data)
    

def eggTurner():
    current_time = datetime.now()
    global last_relay_on
    global eggPin
    day_in_cycle = day()
    if day_in_cycle <18:
        if last_relay_on is None:
            last_relay_on = datetime.now()
            eggPin = 0
        if eggPin == 0:
            if current_time - last_relay_on >= timedelta(seconds=relay_interval):
                # Turn on the relay for 2 minutes
                GPIO.output(egg_turner_relay_pin, GPIO.LOW)
                eggPin = 1
                last_relay_on = current_time
        elif eggPin == 1:        
            if current_time - last_relay_on >= timedelta(seconds=roll_interval):
                GPIO.output(egg_turner_relay_pin, GPIO.HIGH)
                eggPin = 0

    return last_relay_on


def control():
    temperature, humidity = read_sensor_data()
    global temperature_relay_status
    global humidity_relay_status
    if temperature < temperature_threshold:
        # Turn on the heat source
        GPIO.output(heat_relay_pin, GPIO.LOW)
        temperature_relay_status = "ON"
    else:
        # Turn off the heat source
        GPIO.output(heat_relay_pin, GPIO.HIGH)
        temperature_relay_status = "OFF"
    # Check if the humidity is above the threshold
    if humidity < humidity_threshold:
        # Turn off the humidifier
        GPIO.output(humidifier_relay_pin, GPIO.LOW)
        humidity_relay_status = "ON"
    else:
        # Turn on the humidifier
        GPIO.output(humidifier_relay_pin, GPIO.HIGH)
        humidity_relay_status = "OFF"
    

def day():
    global humidity_threshold
    current_date = datetime.now()
    total_days = 21
    day_in_cycle = (current_date - start_date).days % total_days
    if day_in_cycle >= 18:
        humidity_threshold = 70
    return day_in_cycle

def update_config(variable, value):
    with open("config.json", "r") as config_file:
        config = json.load(config_file)
        config[variable] = value
    with open("config.json", "w") as config_file:
        json.dump(config, config_file) 

def clear_database():
    incubator.drop()


def read_and_log_data():
    global dataLogged
    try:
        while True:
            day_in_cycle = day()
            control()
            last_relay_on = eggTurner()
            temperature, humidity = read_sensor_data()
            if dataLogged is None:
                dataLogged = datetime.now()
                log_data(temperature, humidity, last_relay_on,temperature_relay_status,humidity_relay_status, day_in_cycle)
                
            elif datetime.now() - dataLogged >= timedelta(seconds=log_interval):
                dataLogged = datetime.now()
                log_data(temperature, humidity, last_relay_on,temperature_relay_status,humidity_relay_status, day_in_cycle)
               
            
            time.sleep(10)
            
    except KeyboardInterrupt:
        pass
    finally:
        # Clean up the GPIO pins
        GPIO.cleanup()
        # Close the MongoDB connection
        client.close()
        




@app.route("/")
def index():
        day_in_cycle = day()
        thread = Thread(target=read_and_log_data)
        thread.start()
        temperature, humidity = read_sensor_data()
        last_relay_on = eggTurner()
        last_relay_on = last_relay_on.strftime("%m-%d-%Y %I:%M %P")
        
        
        # Fetch the data from the MongoDB collection
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
                'Day in Egg Cycle' : data['Day in Egg Cycle']
            })
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
            'start_date': start_date.strftime("%m-%d-%Y")
        }
        return render_template('index.html',data=data)

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
        log_interval = int(value)*60
    elif variable == 'relay_interval':
        relay_interval = int(value)*60*60
    elif variable == 'roll_interval':
        roll_interval = int(value)*60
    elif variable == 'start_date':
        date = datetime.strptime(value, '%m/%d/%Y')
        start_date = datetime(date.year,date.month,date.day)
        formatted_date = date.strftime('%Y-%m-%d')
        update_config('start_date', formatted_date)
        clear_database()
    return jsonify({'status': 'success'})


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')