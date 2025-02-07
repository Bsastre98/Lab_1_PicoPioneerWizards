import time
from machine import *
from Displays import *
from Lights import *
from Motors import *
from Buzzer import *
from Log import *
from StateModel import *
from dht import *
from LightStrip import *


# ---------------------------------------------------
# Temperature Sensor Class
# ---------------------------------------------------
class TemperatureSensor:
    def __init__(self, pin=6):  
        self.sensor = DHT11(Pin(pin))

    def read_temperature(self):
        """Reads the temperature from the DHT11 sensor and returns the value in °C."""
        try:
            self.sensor.measure()  # Trigger a new reading
            temp = self.sensor.temperature()  # Get temperature (°C)
            hum = self.sensor.humidity()  # Get humidity (%)
            Log.i(f"Temperature: {temp}°C, Humidity: {hum}%")
            return temp  # Return temperature only
        except OSError as e:
            Log.e("Error reading DHT11 sensor: " + str(e))
            return None  # Return None if there’s an error

# ---------------------------------------------------
# Temperature Fan Control (using PassiveBuzzer with hazard sound)
# ---------------------------------------------------
class TemperatureFanControl:
    def __init__(self):
        # Temperature thresholds
        self.FAN1_THRESHOLD = 30      # Temperature (°C) to turn on Fan 1
        self.FAN2_THRESHOLD = 40      # Temperature (°C) to turn on Fan 2 (both fans on)
        self.CRITICAL_THRESHOLD = 50  # Temperature (°C) to trigger critical state

        # Initialize hardware components
        self.lcd = LCDDisplay(sda=0, scl=1)
        self.fan1 = CoolingFan(enable_pin=14, name="Fan 1")
        self.fan2 = CoolingFan(enable_pin=15, name="Fan 2")
        self.led_strip = LightStrip(pin=12, name="Temperature LED", numleds=8)
        #  PassiveBuzzer here 
        self.buzzer = PassiveBuzzer(pin=8, name="Warning Buzzer")
        self.sensor = TemperatureSensor(pin=6)  # Real sensor

        # Initialize the StateModel with 4 states (0, 1, 2, 3)
        self._model = StateModel(4, self, debug=True)

        # Register custom events
        self._model.addCustomEvent("fan1_on")
        self._model.addCustomEvent("both_fans_on")
        self._model.addCustomEvent("critical_temp")
        self._model.addCustomEvent("temp_drop")

        # Define upward transitions:
        #   0 (Idle) --[fan1_on]--> 1 (Fan 1 On)
        #   1 (Fan 1 On) --[both_fans_on]--> 2 (Both Fans On)
        #   2 (Both Fans On) --[critical_temp]--> 3 (Critical)
        self._model.addTransition(0, ["fan1_on"], 1)
        self._model.addTransition(1, ["both_fans_on"], 2)
        self._model.addTransition(2, ["critical_temp"], 3)

        # Define downward transitions:
        #   3 (Critical) --[temp_drop]--> 2 (Both Fans On)
        #   2 (Both Fans On) --[temp_drop]--> 1 (Fan 1 On)
        #   1 (Fan 1 On) --[temp_drop]--> 0 (Idle)
        self._model.addTransition(3, ["temp_drop"], 2)
        self._model.addTransition(2, ["temp_drop"], 1)
        self._model.addTransition(1, ["temp_drop"], 0)

    def read_temperature(self):
        """Fetches the temperature from the DHT11 sensor."""
        temp = self.sensor.read_temperature()
        return temp if temp is not None else 25  # Default to 25°C if error

    def update_system(self):
        """Determines the desired state based on temperature and triggers state transitions."""
        temperature = self.read_temperature()
        Log.i(f"Current Temperature: {temperature}°C")
        
        # Update the LCD with the current temperature.
        self.lcd.clear()
        self.lcd.showText(f"Temp: {temperature}C", row=0, col=0)

        # Determine the desired state based on temperature:
        #   State 0: below 30°C, State 1: 30°C-39°C, State 2: 40°C-49°C, State 3: 50°C and above
        if temperature >= self.CRITICAL_THRESHOLD:
            desired_state = 3
        elif temperature >= self.FAN2_THRESHOLD:
            desired_state = 2
        elif temperature >= self.FAN1_THRESHOLD:
            desired_state = 1
        else:
            desired_state = 0

        # Get the current state from the state model.
        current_state = self._model._curState  # (Assuming direct access to _curState)

        # Transition upward 
        while current_state < desired_state:
            if current_state == 0:
                self._model.processEvent("fan1_on")
            elif current_state == 1:
                self._model.processEvent("both_fans_on")
            elif current_state == 2:
                self._model.processEvent("critical_temp")
            current_state = self._model._curState  # Update current state

        # Transition downward 
        while current_state > desired_state:
            self._model.processEvent("temp_drop")
            current_state = self._model._curState  # Update current state

    def warning_beep(self):
        """
        Implements a hazard sound pattern:
        The buzzer will be on for 300 ms and off for 300 ms in a continuous loop.
        """
        current_time = time.ticks_ms()
        
        if (current_time % 200) < 100:
            self.buzzer.play(tone=1000)  # Play a 1 kHz tone 
        else:
            self.buzzer.stop()

    def stateEvent(self, state, event):
        """Called when an in-state event occurs (if needed)."""
        Log.d(f"State {state}: Processing event {event}")

    def stateEntered(self, state, event):
        """Called when entering a new state; sets up the hardware accordingly."""
        Log.d(f"Entered State {state} on event {event}")
        if state == 0:
            # Idle: Turn off fans and buzzer, set LED to blue.
            self.fan1.stop()
            self.fan2.stop()
            self.buzzer.stop()
            self.led_strip.setColor((0, 0, 255))  # Blue
            self.lcd.showText("State: Idle", row=1, col=0)
        elif state == 1:
            # 30°C: Turn on Fan 1 at moderate speed, LED green.
            self.fan1.run(50)
            self.led_strip.setColor((0, 255, 0))  # Green
            self.lcd.showText("State: Fan 1 On", row=1, col=0)
        elif state == 2:
            # 40°C: Run both fans at higher speed, LED yellow.
            self.fan1.run(75)
            self.fan2.run(75)
            self.led_strip.setColor((255, 255, 0))  # Yellow
            self.lcd.showText("State: Both Fans On", row=1, col=0)
        elif state == 3:
            # 50°C and above: Critical state.
            # Run both fans and prepare the hazard tone.
            self.fan1.run(75)
            self.fan2.run(75)
            # Do not call buzzer.play() here; let the hazard pattern in stateDo handle it.
            self.buzzer.stop()  # Ensure the buzzer is off before the hazard pattern takes over.
            self.led_strip.setColor((255, 0, 0))  # Red
            self.lcd.showText("State: Warning! High Temp", row=1, col=0)

    def stateLeft(self, state, event):
        """Called when leaving a state; performs cleanup as needed."""
        Log.d(f"Left State {state} on event {event}")
        if state == 3:
            self.buzzer.stop()
        if state == 2 and event != "critical_temp":
            self.fan2.stop()
        if state == 1:
            self.fan1.stop()

    def stateDo(self, state):
        """
        This method is called repeatedly in the state’s execution loop.
        If in the critical state, it continuously runs the hazard beep pattern.
        """
        if state == 3:
            self.warning_beep()
        self.update_system()

    def run(self):
        """Starts the state model loop."""
        self._model.run()

# ---------------------------------------------------
# Main entry point
# ---------------------------------------------------
if __name__ == "__main__":
    controller = TemperatureFanControl()
    controller.run()
