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


class IncubatorController:
    def __init__(self, config_file_path):
        with open(config_file_path) as config_file:
            config = json.load(config_file)

        self.start_date = datetime.strptime(config['start_date'], '%Y-%m-%d')

        # Connect to MongoDB
        uri = config['uri']
        client = MongoClient(uri)
        self.db = client[config['database']]
        self.incubator = self.db[config['collection']]

        # Set the sensor type (DHT22) and the GPIO pin number
        self.i2c = board.I2C()
        self.sensor = adafruit_ahtx0.AHTx0(self.i2c)

        # Set the relay pin number
        self.egg_turner_relay_pin = 19
        self.heat_relay_pin = 21
        self.humidifier_relay_pin = 20

        # Set the interval for logging data and turning on the relay (in seconds)
        self.log_interval = config['log_interval']
        self.relay_interval = config['relay_interval']
        self.roll_interval = config['roll_interval']
        self.last_relay_on = config['last_relay_on']
        self.temperature_relay_status = config['temperature_relay_status']
        self.humidity_relay_status = config['humidity_relay_status']
        self.day_in_cycle = config['day_in_cycle']

        # Set the temperature and humidity thresholds
        self.temperature_threshold = 100
        self.humidity_threshold = 50

        # Setup the Flask app
        self.app = Flask(__name__, static_folder='static')

        # Initialize the GPIO pins
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.heat_relay_pin, GPIO.OUT)
        GPIO.setup(self.humidifier_relay_pin, GPIO.OUT)
        GPIO.setup(self.egg_turner_relay_pin, GPIO.OUT)

    def read_sensor_data(self):
        # Read the humidity and temperature
        humidity, temperature = self.sensor.relative_humidity, self.sensor.temperature
        if humidity is not None and temperature is not None:
            temperature = (temperature * 9/5) + 32
            return round(temperature,1), round(humidity,1)
        else:
            print('Failed to read data from sensor')
            return None, None
    

    def log_data(self,temperature, humidity):
        # Get the most recent record from the database
        last_record = self.incubator.find_one(sort=[('_id', pymongo.DESCENDING)])

        # Check if a record has been stored within the log interval
        if last_record is None or (datetime.now() - datetime.strptime(last_record['Time'], '%m-%d-%Y %H:%M')).total_seconds() >= self.log_interval:
            # Create a data dictionary
            data = {
                'Time': time.strftime("%m-%d-%Y %H:%M"),
                'Temperature(F)': temperature,
                'Temperature Relay Status': self.temperature_relay_status,
                'Humidity(%)': humidity,
                'Humidity Relay Status': self.humidity_relay_status,
                'Last Egg Turn': self.last_relay_on.strftime("%m-%d-%Y %I:%M %P") if self.last_relay_on is not None else '',
                'Day in Egg Cycle': self.day_in_cycle
            }

            # Insert the data into the incubator collection
            self.incubator.insert_one(data)  


    def egg_turner(self):
        current_time = datetime.now()
        if self.day_in_cycle < 18:
            if self.last_relay_on is None:
                self.last_relay_on = datetime.now()
            if GPIO.input(self.egg_turner_relay_pin) == 1:
                if current_time - self.last_relay_on >= timedelta(seconds=self.relay_interval):
                    # Turn on the relay for 2 minutes
                    GPIO.output(self.egg_turner_relay_pin, GPIO.LOW)
                    self.last_relay_on = current_time
            elif GPIO.input(self.egg_turner_relay_pin) == 0:
                if current_time - self.last_relay_on >= timedelta(seconds=self.roll_interval):
                    GPIO.output(self.egg_turner_relay_pin, GPIO.HIGH)
        return self.last_relay_on


    def control(self):
        temperature, humidity = self.read_sensor_data()

        if temperature < self.temperature_threshold - 1:
            # Turn on the heat source
            GPIO.output(self.heat_relay_pin, GPIO.LOW)
            if GPIO.input(self.heat_relay_pin) == 0:
                self.temperature_relay_status = "ON"
            else:
                print("HEAT GPIO not setting to low or ON")
        elif temperature > self.temperature_threshold:
            # Turn off the heat source
            GPIO.output(self.heat_relay_pin, GPIO.HIGH)
            if GPIO.input(self.heat_relay_pin) == 1: 
                self.temperature_relay_status = "OFF"
            else:
                print("HEAT GPIO not setting to High or OFF")
        else:
            # Do nothing
            pass

        if humidity < (self.humidity_threshold - 5):
            # Turn on the humidifier
            GPIO.output(self.humidifier_relay_pin, GPIO.LOW)
            if GPIO.input(self.humidifier_relay_pin) == 0:
                self.humidity_relay_status = "ON"
            else:
                print("HUMIDITY GPIO not setting to low or ON")
        else:
            # Turn off the humidifier
            GPIO.output(self.humidifier_relay_pin, GPIO.HIGH)
            if GPIO.input(self.humidifier_relay_pin) == 1:
                self.humidity_relay_status = "OFF"
            else:
                print("HUMIDITY GPIO not setting to HIGH or OFF")

    def day(self):
        current_date = datetime.now()
        total_days = 21
        day_in_cycle = (current_date - self.start_date).days % total_days
        if day_in_cycle >= 18:
            self.humidity_threshold = 75
        return day_in_cycle

    def lock_down_and_hatch(self):
        lock_down_date = self.start_date + timedelta(days=18)
        hatch_date = self.start_date + timedelta(days=21)
        return lock_down_date,hatch_date

    def update_config(self, variable, value):
        with open("config.json", "r") as config_file:
            config = json.load(config_file)
            config[variable] = value
        with open("config.json", "w") as config_file:
            json.dump(config, config_file)

    def clear_database(self):
        self.incubator.drop()

    def read_and_log_data(self):
        try:
            while True:
                self.day_in_cycle = self.day()
                self.control()
                self.last_relay_on = self.egg_turner()
                temperature, humidity = self.read_sensor_data()
                self.log_data(temperature, humidity)
                time.sleep(20)
        except KeyboardInterrupt:
            pass
        finally:
            # Clean up the GPIO pins
            GPIO.cleanup()
            # Close the MongoDB connection
            self.db.client.close()
    
    def get_egg_cycle_statistics(self, historical_data):
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

    def run(self):
        thread = Thread(target=self.read_and_log_data)
        thread.start()
        self.app.run(debug=True, host='0.0.0.0')

        

if __name__ == '__main__':
    IncubatorController('config.json').run()