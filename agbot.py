from XRPLib.encoded_motor import EncodedMotor
from XRPLib.pid import PID
from XRPLib.timeout import Timeout
import time
import math

from pump import Pump
from moisture import MoistureSensor
from xy_motion import XY_motion
from z_motion import Z_motion

class AgBot():
    @classmethod
    def get_default_agbot(cls, x_size = None, y_size = None):
        xy = XY_motion.get_default_xy()
        z = Z_motion.get_default_z()
        pump = Pump.get_default_pump()
        moisture = MoistureSensor.get_default_moisture_sensor()
        return AgBot(xy, z, pump, moisture)
    
    def stop(self):
        self.xy.stop()
        self.z.stop()
        self.pump.stop()

    def __init__(self, xy, z, pump, moisture):
        self.xy = xy
        self.z = z
        self.pump = pump
        self.sensor = moisture

        self.stop()

    async def home(self):
        await self.z.home()
        await self.z.up()
        await self.xy.home()
    
    async def find_size(self):
        await self.z.up()
        return await self.xy.find_size()
    
    async def move_to(self, x, y):
        print("agbot Moving to: ", x, y)
        # self.z.up()
        await self.xy.move_to(x, y)
        
    async def move_relative_xy(self, dx, dy):
        await self.xy.move_relative_xy(dx, dy)

    async def read(self):
        await self.z.down()
        reading = self.sensor.read()
        await self.z.up()
        return reading
    
    async def water(self, ml):
        await self.pump.water(ml)
        
    def manual(self):
        # home and move a little to the center  
        print(" You are in Manual Control Mode for AgBot")
        print("Command Options, type them to use them")
        print("1: home")
        print("2: find size")
        print("3: get xy position")
        print("4: set xy position")
        print("5: watering")
        print("6: moisture sensing")
        print("7: exit")
        print("")
        
        while(True):
            choice = int(input("Enter choice: "))
            if choice == 1:
                self.home()
            elif choice == 2:
                self.find_size()
            elif choice == 3:
                print("Position: ", self.xy.get_position())
            elif choice == 4:
                x = int(input("Enter x: "))
                y = int(input("Enter y: "))
                self.move_to(x, y)
            elif choice == 5:
                ml = int(input("Enter ml: "))
                self.water(ml)
            elif choice == 6:
                print("Moisture read: ", self.read())
            elif choice == 7:
                return
            else:
                print("Invalid command")
            time.sleep(.1)
        
if __name__ == "__main__":
    pass
    # encMotor1 = EncodedMotor.get_default_encoded_motor(1)
    # encMotor2 = EncodedMotor.get_default_encoded_motor(2)    
    # encMotor3 = EncodedMotor.get_default_encoded_motor(3)
    # encMotor4 = EncodedMotor.get_default_encoded_motor(4)
    
    # xy = XY(encMotor1, encMotor2, 385, 265)
    # z = Z(encMotor4)
    # pump = Pump(encMotor3)
    # ms = MoistureSensor()
    
    gantry = AgBot.get_default_agbot(x_size = 385, y_size = 265)
    gantry.manual()