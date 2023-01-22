Egg Incubator
This project is a temperature and humidity monitoring and control system for an egg incubator using a Raspberry Pi, a DHT22 sensor, and a relay. The system logs the temperature and humidity data, and turns on a heating element every 4 hours to maintain the desired incubation conditions.

Getting Started
These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

Prerequisites
Raspberry Pi
DHT22 sensor
Relay
Python 3
Flask
pandas
pymongo (if using MongoDB)
Adafruit_DHT library
RPi.GPIO library


Installing
Clone the repository to your Raspberry Pi

git clone https://github.com/[username]/egg-incubator.git
Install the required libraries

pip install -r requirements.txt
Connect the DHT22 sensor to the Raspberry Pi according to the Adafruit_DHT library's instructions
Connect the relay to the Raspberry Pi according to your relay's specifications
Update the uri variable in the script with your MongoDB connection string
Running the script
Navigate to the project directory

cd egg-incubator
Run the script


python egg_incubator.py


The script will start logging the temperature and humidity data, and turning on the heating element every 4 hours. The data will be logged to a CSV file or MongoDB collection depending on your implementation.
The script will also start a local web server, you can access the data visualization by opening http://127.0.0.1:5000/ in your web browser.
Built With
Python - Programming language
Flask - Web framework
pandas - Data manipulation library
pymongo - MongoDB library
Adafruit_DHT - DHT22 sensor library
RPi.GPIO - RPi GPIO library
Contributing
Please read [CONTRIBUTING.md](https://gist.github.com/PurpleBooth/b2467940