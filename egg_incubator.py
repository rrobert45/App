import json
import pandas as pd
from flask import Flask, render_template
import time
import Adafruit_DHT
import RPi.GPIO as GPIO
from threading import Thread
import os
from pymongo import MongoClient
import smtplib
import datetime

# Load the config file
with open('config.json') as config_file:
    config = json.load(config_file)

# Connect to MongoDB
client = MongoClient(config['uri'])
db = client.EggApp
incubator = db.incubator

app = Flask(__name__, static_folder='static')

# Set the sensor type (DHT22) and the GPIO pin number
sensor = Adafruit_DHT.DHT22
pin = config['pin']

# Set the relay pin numbers
humidity_relay = config['humidity_relay']
temperature_relay = config['temperature_relay']
roller_relay = config['roller_relay']

# Set the interval for logging data and turning on the relay (in seconds)
log_interval = config['log_interval']
relay_interval = config['relay_interval']
roll_interval = config['roll_interval']

# Initialize the GPIO pins for the relays
GPIO.setmode(GPIO.BCM)
GPIO.setup(humidity_relay, GPIO.OUT)
GPIO.setup(temperature_relay, GPIO.OUT)

last_relay_on = time.time()

# Set the email address and password for the email alert
email_address = config['email_address']
email_password = config['email_password']



# Set the start date
start_date = datetime.datetime.strptime(config['start_date'], '%m/%d/%Y %I:%M%p')
def read_sensor_data():
    # Read the humidity and temperature
    humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
    if humidity is not None and temperature is not None:
        temperature = (temperature * 9/5) + 32
        return round(temperature,0), round(humidity,0)
    else:
        print('Failed to read data from sensor')
        return None, None

def log_data(temperature, humidity, eggroller_relay_status, temperature_relay_status, humidity_relay_status, day_in_cycle):
    # Create a data dictionary
    data = {
        'Time': time.strftime("%m-%d-%Y %H:%M:%S"),
        'Temperature(F)': temperature,
        'Temperature Relay': temperature_relay_status,
        'Humidity(%)': humidity,
        'Humidity Relay': humidity_relay_status,
        'Eggroller Relay': eggroller_relay_status,
        'Day in Cycle': day_in_cycle
    }
    # Insert the data into the incubator collection
    incubator.insert_one(data)

def sensor_control():

    global temperature_relay_status
    global humidity_relay_status
    global day_in_cycle
    global temperature
    global humidity

    while True:
        temperature, humidity = read_sensor_data()
        start_time = datetime.strptime(start_date, '%Y-%m-%d')
        current_time = datetime.now()
        day_in_cycle = (current_time - start_time).days
        if temperature <= 100:
            GPIO.output(temperature_relay, GPIO.HIGH)
            temperature_relay_status = "ON"
        elif temperature >= 101:
            GPIO.output(temperature_relay, GPIO.LOW)
            temperature_relay_status = "OFF"
        else:
            pass
            
        if day_in_cycle <= 17:
            if humidity < 50:
                GPIO.output(humidity_relay, GPIO.HIGH)
                humidity_relay_status = "ON"
            else:
                GPIO.output(humidity_relay, GPIO.LOW)
                humidity_relay_status = "OFF"
        elif day_in_cycle > 17:
            if humidity < 70:
                GPIO.output(humidity_relay, GPIO.HIGH)
                humidity_relay_status = "ON"
            else:
                GPIO.output(humidity_relay, GPIO.LOW)
                humidity_relay_status = "OFF"
        
        time.sleep(10)



def check_relay():
    current_time = time.time()
    global last_relay_on
    temperature, humidity = read_sensor_data()
    if current_time - last_relay_on >= relay_interval:
        # Turn on the relay for 2 minutes
        GPIO.output(roller_relay, GPIO.HIGH)
        last_relay_on = current_time
        log_data(temperature, humidity, "ON",temperature_relay_status,humidity_relay_status,day_in_cycle)
        time.sleep(roll_interval)
        GPIO.output(roller_relay, GPIO.LOW)
        log_data(temperature, humidity, "OFF",temperature_relay_status,humidity_relay_status,day_in_cycle)
    else:
        log_data(temperature, humidity, "OFF",temperature_relay_status,humidity_relay_status,day_in_cycle)

   

def read_and_log_data():
    try:
        while True:
            check_relay()
            time.sleep(log_interval)
    except KeyboardInterrupt:
        pass
    finally:
        # Clean up the GPIO pins
        GPIO.cleanup()
        # Close the MongoDB connection
        client.close()


@app.route("/")
def index():
        sensor_thread = Thread(target=sensor_control)
        sensor_thread.start()
        thread = Thread(target=read_and_log_data)
        thread.start()
        
        last_relay_on_time = time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(last_relay_on))
        # Fetch the data from the MongoDB collection
        cursor = incubator.find({"Relay Status": "ON"}).sort("Time", -1).limit(10)
        relay_data = []
        for data in cursor:
            relay_data.append({
                'Time': data['Time'],
                'Temperature(F)': data['Temperature(F)'],
                'Humidity(%)': data['Humidity(%)'],
                'Relay Status': data['Relay Status']
            })
        cursor = incubator.find().limit(48).sort("Time", -1)
        historical_data = []
        for data in cursor:
            historical_data.append({
                'Time': data['Time'],
                'Temperature(F)': data['Temperature(F)'],
                'Humidity(%)': data['Humidity(%)'],
                'Relay Status': data['Relay Status']
            })
        return render_template('index.html', historical_data=historical_data, relay_data=relay_data, temperature=temperature, humidity=humidity, last_relay_on=last_relay_on_time,temperature_relay_status=temperature_relay_status,humidity_relay_status=humidity_relay_status)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')