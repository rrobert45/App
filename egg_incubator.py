import pandas as pd
from flask import Flask, render_template
import time
import Adafruit_DHT
import RPi.GPIO as GPIO
from threading import Thread
import os
from pymongo import MongoClient
from datetime import datetime, timedelta

# Connect to MongoDB
uri = "mongodb+srv://rrobert45:pa55word@cluster0.r8sgbwj.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(uri)
db = client.EggApp
incubator = db.incubator

print(os.getcwd())

app = Flask(__name__, static_folder='static')

# Set the sensor type (DHT22) and the GPIO pin number
sensor = Adafruit_DHT.DHT22
pin = 4

# Set the relay pin number
egg_turner_relay_pin = 17
heat_relay_pin = 18
humidifier_relay_pin = 19

# Set the interval for logging data and turning on the relay (in seconds)
log_interval = 60*15 # 15 minutes time between logging data to the database 
relay_interval = 60*60*2 # 2 hours between turning the eggs
roll_interval = 3*60 #how long to turn the eggs
last_relay_on = None
dataLogged = None

# Set the temperature and humidity thresholds
temperature_threshold = 100
humidity_threshold = 20

# Initialize the GPIO pins
GPIO.setmode(GPIO.BCM)
GPIO.setup(heat_relay_pin, GPIO.OUT)
GPIO.setup(humidifier_relay_pin, GPIO.OUT)
GPIO.setup(egg_turner_relay_pin, GPIO.OUT)




def read_sensor_data():
    # Read the humidity and temperature
    humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
    if humidity is not None and temperature is not None:
        temperature = (temperature * 9/5) + 32
        return round(temperature,1), round(humidity,1)
    else:
        print('Failed to read data from sensor')
        return None, None

def log_data(temperature, humidity, last_relay_on,temperature_relay_status,humidity_relay_status):
    # Create a data dictionary
    data = {
        'Time': time.strftime("%m-%d-%Y %H:%M:%S"),
        'Temperature(F)': temperature,
        'Temperature Relay Status': temperature_relay_status,
        'Humidity(%)': humidity,
        'Humidity Relay Status': humidity_relay_status,
        'Last Egg Turn': last_relay_on
    }
    # Insert the data into the incubator collection
    incubator.insert_one(data)



def eggTurner():
    
    current_time = datetime.now()
    if last_relay_on is None:
        last_relay_on = datetime.now()
        eggPin = 0
    if eggPin == 0:
        if current_time - last_relay_on >= timedelta(seconds=relay_interval):
            # Turn on the relay for 2 minutes
            GPIO.output(egg_turner_relay_pin, GPIO.HIGH)
            eggPin = 1
            last_relay_on = current_time
    elif eggPin == 1:        
        if current_time - last_relay_on >= timedelta(seconds=roll_interval):
            GPIO.output(egg_turner_relay_pin, GPIO.LOW)
            eggPin = 0
    return last_relay_on

def control():
    temperature, humidity = read_sensor_data()
    if temperature < temperature_threshold:
        # Turn on the heat source
        GPIO.output(heat_relay_pin, GPIO.HIGH)
        temperature_relay_status = "ON"
    else:
        # Turn off the heat source
        GPIO.output(heat_relay_pin, GPIO.LOW)
        temperature_relay_status = "OFF"
    # Check if the humidity is above the threshold
    if humidity > humidity_threshold:
        # Turn off the humidifier
        GPIO.output(humidifier_relay_pin, GPIO.LOW)
        humidity_relay_status = "OFF"
    else:
        # Turn on the humidifier
        GPIO.output(humidifier_relay_pin, GPIO.HIGH)
        humidity_relay_status = "OFF"
    
    return temperature_relay_status, humidity_relay_status





def read_and_log_data():
    
    try:
        while True:
            last_relay_on = eggTurner()
            temperature_relay_status, humidity_relay_status = control()
            temperature, humidity = read_sensor_data()
            if dataLogged is None:
                dataLogged = datetime.now()
                log_data(temperature, humidity, last_relay_on,temperature_relay_status,humidity_relay_status)
            elif (datetime.now() - dataLogged).total_seconds() >= log_interval:
                dataLogged = datetime.now()
                log_data(temperature, humidity, last_relay_on,temperature_relay_status,humidity_relay_status)
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
        last_relay_on = eggTurner()
        temperature_relay_status, humidity_relay_status = control()
        thread = Thread(target=read_and_log_data)
        thread.start()
        temperature, humidity = read_sensor_data()
        last_relay_on_time = time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(last_relay_on))
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
                'Last Egg Turn': data['Last Egg Turn']
            })
        return render_template('index.html', historical_data=historical_data, temperature=temperature, humidity=humidity, last_relay_on=last_relay_on_time, temperature_relay_status=temperature_relay_status, humidity_relay_status=humidity_relay_status)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')

