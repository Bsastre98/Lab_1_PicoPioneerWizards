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
    """
    A class to interface with the DHT11 temperature/humidity sensor.
    """
    def __init__(self, pin=6):
        """
        Initialize the DHT11 sensor.

        :param pin: Microcontroller pin number to which DHT11 is connected.
        """
        self.sensor = DHT11(Pin(pin))

    def read_temperature(self):
        """
        Reads the temperature from the DHT11 sensor and returns the value in °C.
        Logs both temperature and humidity.

        :return: Temperature in °C or None if an error occurred.
        """
        try:
            self.sensor.measure()  # Trigger a new reading
            temp = self.sensor.temperature()  # Get temperature (°C)
            hum = self.sensor.humidity()      # Get humidity (%)
            Log.i(f"Temperature: {temp}°C, Humidity: {hum}%")
            return temp
        except OSError as e:
            # In case of sensor read error, log an error and return None
            Log.e("Error reading DHT11 sensor: " + str(e))
            return None

# ---------------------------------------------------
# Temperature Fan Control (using PassiveBuzzer with hazard sound)
# ---------------------------------------------------
class TemperatureFanControl:
    """
    Orchestrates the temperature measurement, fan control, LED alerts,
    and buzzer warnings based on temperature thresholds.
    """
    def __init__(self):
        """
        Initialize hardware components, threshold values, and the StateModel.
        """
        # Define temperature thresholds in °C
        self.FAN1_THRESHOLD = 30      # Turn on Fan 1 at 30°C
        self.FAN2_THRESHOLD = 40      # Turn on Fan 2 at 40°C (both fans)
        self.CRITICAL_THRESHOLD = 50  # Trigger critical state at 50°C

        # Initialize hardware components
        self.lcd = LCDDisplay(sda=0, scl=1)      # I2C LCD Display
        self.fan1 = CoolingFan(enable_pin=14, name="Fan 1")
        self.fan2 = CoolingFan(enable_pin=15, name="Fan 2")
        self.led_strip = LightStrip(pin=12, name="Temperature LED", numleds=8)
        self.buzzer = PassiveBuzzer(pin=8, name="Warning Buzzer")
        self.sensor = TemperatureSensor(pin=6)   # Real DHT11 sensor

        # Initialize the StateModel with 4 states (0, 1, 2, 3)
        # 0 -> Idle
        # 1 -> Fan 1 On
        # 2 -> Both Fans On
        # 3 -> Critical
        self._model = StateModel(4, self, debug=True)

        # Register custom events to trigger transitions
        self._model.addCustomEvent("fan1_on")
        self._model.addCustomEvent("both_fans_on")
        self._model.addCustomEvent("critical_temp")
        self._model.addCustomEvent("temp_drop")

        # Define upward transitions
        # 0 (Idle) --[fan1_on]--> 1 (Fan 1 On)
        # 1 (Fan 1 On) --[both_fans_on]--> 2 (Both Fans On)
        # 2 (Both Fans On) --[critical_temp]--> 3 (Critical)
        self._model.addTransition(0, ["fan1_on"], 1)
        self._model.addTransition(1, ["both_fans_on"], 2)
        self._model.addTransition(2, ["critical_temp"], 3)

        # Define downward transitions
        # 3 (Critical) --[temp_drop]--> 2 (Both Fans On)
        # 2 (Both Fans On) --[temp_drop]--> 1 (Fan 1 On)
        # 1 (Fan 1 On) --[temp_drop]--> 0 (Idle)
        self._model.addTransition(3, ["temp_drop"], 2)
        self._model.addTransition(2, ["temp_drop"], 1)
        self._model.addTransition(1, ["temp_drop"], 0)

    def read_temperature(self):
        """
        Fetches the temperature from the DHT11 sensor.

        :return: Temperature value in °C, or 25°C (default) if None is returned by sensor.
        """
        temp = self.sensor.read_temperature()
        # Default to 25°C if sensor read fails
        return temp if temp is not None else 25

    def update_system(self):
        """
        Determines the desired state based on temperature and triggers
        state transitions to move from the current state to the new state.
        """
        # Measure current temperature
        temperature = self.read_temperature()
        Log.i(f"Current Temperature: {temperature}°C")

        # Update the LCD display with current temperature
        self.lcd.clear()
        self.lcd.showText(f"Temp: {temperature}C", row=0, col=0)

        # Determine desired state based on thresholds
        if temperature >= self.CRITICAL_THRESHOLD:
            desired_state = 3  # Critical
        elif temperature >= self.FAN2_THRESHOLD:
            desired_state = 2  # Both Fans On
        elif temperature >= self.FAN1_THRESHOLD:
            desired_state = 1  # Fan 1 On
        else:
            desired_state = 0  # Idle

        # Get current state from StateModel
        current_state = self._model._curState

        # Transition upward (e.g., from state 0 -> 1 -> 2 -> 3)
        while current_state < desired_state:
            if current_state == 0:
                self._model.processEvent("fan1_on")
            elif current_state == 1:
                self._model.processEvent("both_fans_on")
            elif current_state == 2:
                self._model.processEvent("critical_temp")
            current_state = self._model._curState  # Update after transition

        # Transition downward (e.g., from state 3 -> 2 -> 1 -> 0)
        while current_state > desired_state:
            self._model.processEvent("temp_drop")
            current_state = self._model._curState  # Update after transition

    def warning_beep(self):
        """
        Implements a hazard sound pattern for the passive buzzer:
        - On for 100 ms, off for 100 ms (effectively 200 ms cycle).
        - Tied to current time in milliseconds.
        """
        current_time = time.ticks_ms()

        # This pattern creates a consistent on/off cycle
        if (current_time % 200) < 100:
            self.buzzer.play(tone=1000)  # 1 kHz tone
        else:
            self.buzzer.stop()

    def stateEvent(self, state, event):
        """
        Called when an in-state event occurs (if needed).
        This method can be used for any additional logic while
        remaining in the same state.

        :param state: Current state index.
        :param event: Event name that triggered this call.
        """
        Log.d(f"State {state}: Processing event {event}")

    def stateEntered(self, state, event):
        """
        Called when entering a new state; configure hardware (fans, buzzer, LED, LCD).

        :param state: New state index.
        :param event: Event name that triggered this transition.
        """
        Log.d(f"Entered State {state} on event {event}")

        if state == 0:
            # Idle state: Turn off everything, set LED to blue
            self.fan1.stop()
            self.fan2.stop()
            self.buzzer.stop()
            self.led_strip.setColor((0, 0, 255))  # Blue
            self.lcd.showText("State: Idle", row=1, col=0)

        elif state == 1:
            # Fan 1 on: moderate speed, LED green
            self.fan1.run(50)
            self.led_strip.setColor((0, 255, 0))  # Green
            self.lcd.showText("State: Fan 1 On", row=1, col=0)

        elif state == 2:
            # Both fans on: higher speed, LED yellow
            self.fan1.run(75)
            self.fan2.run(75)
            self.led_strip.setColor((255, 255, 0))  # Yellow
            self.lcd.showText("State: Both Fans On", row=1, col=0)

        elif state == 3:
            # Critical temp: run fans full, hazard tone pattern in stateDo, LED red
            self.fan1.run(75)
            self.fan2.run(75)
            # Ensure buzzer is off here; hazard beep will be triggered in stateDo
            self.buzzer.stop()
            self.led_strip.setColor((255, 0, 0))  # Red
            self.lcd.showText("State: Warning! High Temp", row=1, col=0)

    def stateLeft(self, state, event):
        """
        Called when leaving a state; perform any needed cleanup.

        :param state: Old state index.
        :param event: Event name that caused exiting the state.
        """
        Log.d(f"Left State {state} on event {event}")

        if state == 3:
            # Leaving critical state: stop the buzzer
            self.buzzer.stop()

        # If leaving "Both Fans On" state in non-critical circumstances, turn off second fan
        if state == 2 and event != "critical_temp":
            self.fan2.stop()

        if state == 1:
            # Leaving "Fan 1 On" state: stop fan 1
            self.fan1.stop()

    def stateDo(self, state):
        """
        Called repeatedly in the state's execution loop.
        If in critical state (state 3), run the hazard beep pattern.

        :param state: Current state index.
        """
        if state == 3:
            self.warning_beep()  # Continuous hazard beep pattern for critical temp

        # Always check for temperature changes to adjust state as needed
        self.update_system()

    def run(self):
        """
        Starts the StateModel loop. This blocks and continuously runs
        stateDo() logic for the current state until program ends.
        """
        self._model.run()

# ---------------------------------------------------
# Main entry point
# ---------------------------------------------------
if __name__ == "__main__":
    """
    If the script is run directly, create a TemperatureFanControl instance
    and start its main loop.
    """
    controller = TemperatureFanControl()
    controller.run()
