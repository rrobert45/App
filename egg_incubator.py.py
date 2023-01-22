import pandas as pd
from flask import Flask, render_template
import time
import Adafruit_DHT
import RPi.GPIO as GPIO
from threading import Thread
import os
from pymongo import MongoClient

# Connect to MongoDB
uri = "mongodb+srv://rrobert45:xP4sfa9hsptanQwU@cluster0.r8sgbwj.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(uri)
db = client.EggApp
incubator = db.incubator

print(os.getcwd())

app = Flask(__name__, static_folder='static')

# Set the sensor type (DHT22) and the GPIO pin number
sensor = Adafruit_DHT.DHT22
pin = 4

# Set the relay pin number
relay = 17

# Set the interval for logging data and turning on the relay (in seconds)
log_interval = 1800 # 5 minutes
relay_interval = 14400 # 4 hours

# Initialize the GPIO pin for the relay
GPIO.setmode(GPIO.BCM)
GPIO.setup(relay, GPIO.OUT)

last_relay_on = time.time()

def read_sensor_data():
    # Read the humidity and temperature
    humidity, temperature = Adafruit_DHT.read_retry(sensor, pin)
    if humidity is not None and temperature is not None:
        temperature = (temperature * 9/5) + 32
        return round(temperature,0), round(humidity,0)
    else:
        print('Failed to read data from sensor')
        return None, None

def log_data(temperature, humidity, relay_status):
    # Create a data dictionary
    data = {
        'Time': time.strftime("%m-%d-%Y %H:%M:%S"),
        'Temperature(F)': temperature,
        'Humidity(%)': humidity,
        'Relay Status': relay_status
    }
    # Insert the data into the incubator collection
    incubator.insert_one(data)

def check_relay():
    current_time = time.time()
    global last_relay_on
    if current_time - last_relay_on >= relay_interval:
        temperature, humidity = read_sensor_data()
        # Turn on the relay for 2 minutes
        GPIO.output(relay, GPIO.HIGH)
        last_relay_on = current_time
        log_data(temperature, humidity, "ON")
        time.sleep(120)
        GPIO.output(relay, GPIO.LOW)
        log_data(temperature, humidity, "OFF")
    else:
        pass



def read_and_log_data():
    try:
        while True:
            temperature, humidity = read_sensor_data()
            log_data(temperature, humidity)
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
        thread = Thread(target=read_and_log_data)
        thread.start()
        temperature, humidity = read_sensor_data()
        last_relay_on_time = time.strftime("%m-%d-%Y %H:%M:%S", time.localtime(last_relay_on))
        # Fetch the data from the MongoDB collection
        cursor = incubator.find()
        df =  pd.DataFrame(list(cursor))

        # Format the data for the graph
        x_data = df["Time"].tolist()
        y_data = df["Temperature(F)"].tolist()
        y2_data = df["Humidity(%)"].tolist()

        return render_template('index.html', x_data=x_data, y_data=y_data, y2_data=y2_data, temperature=temperature, humidity=humidity, last_relay_on=last_relay_on_time)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')