from XRPLib.encoded_motor import EncodedMotor
from XRPLib.pid import PID
from XRPLib.timeout import Timeout
import time
import math

import uasyncio as asyncio

class default_pump:
    # Default motor for the pump
    MOTOR = EncodedMotor.get_default_encoded_motor(3)
    
    # Amount of turns to dispense 1 ml
    TURNS_TO_ML = 1.5
    # Amount of liquid to purge before dispensing
    PURGE_ML = 10
    
    ## Positive or Negative results in dispense
    # Positive: 1
    # Negative: -1
    DISPENSE_DIRECTION = 1

def bound_effort(value, max_effort=1.0):
    return max(0, min(max_effort, value))

class Pump(EncodedMotor):
    @classmethod
    def get_default_pump(cls):
        motor = default_pump.MOTOR
        turns_to_ml = default_pump.TURNS_TO_ML
        purge_ml = default_pump.PURGE_ML
        dispense_direction = default_pump.DISPENSE_DIRECTION
        return Pump(motor, turns_to_ml, purge_ml, dispense_direction)
    
    def stop(self):
        self.motor_pump.set_effort(0)

    def __init__(self, 
            motor_pump, turns_to_ml, purge_ml: float, dispense_direction: int):
        self.motor_pump = motor_pump
        self.turns_to_ml = turns_to_ml
        self.purge_ml = purge_ml
        self.dispense_direction = dispense_direction

        self.stop()

    async def turn(self, turns: float):
        start_position = self.motor_pump.get_position()
        self.motor_pump.set_effort(self.dispense_direction)
        while abs(start_position - self.motor_pump.get_position()) < turns:
            await asyncio.sleep(0.1)

        self.motor_pump.set_effort(0)
        
    async def water(self, ml: float):
        turns = ml * self.turns_to_ml
        await self.turn(turns)

if __name__ == "__main__":
    p = Pump.get_default_pump()
    p.pump(5)
