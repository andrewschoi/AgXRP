from XRPLib.encoded_motor import EncodedMotor
from XRPLib.pid import PID
from XRPLib.timeout import Timeout
import time
import math
import uasyncio as asyncio

def bound_effort(value, max_effort=1.0):
        return max(0, min(max_effort, value))

class default_z_params:
    GEAR_DIAMETER = 12 # mm
    TURNS_TO_MM = GEAR_DIAMETER * math.pi
    TRAVEL_DISTANCE = 20
    
    ### what effort sign is up
    # default is positive
    DEFAULT_UP_EFFORT = -1 # -1 or 1
    
    ### safe height to move xy at
    Z_SAFE_MOVE_HEIGHT = 10 # mm

class Z_motion:
    @classmethod
    def get_default_z(cls):
        z_motor = EncodedMotor.get_default_encoded_motor(4)
        up_sign = default_z_params.DEFAULT_UP_EFFORT
        motor_turns_to_mm = default_z_params.TURNS_TO_MM
        z_safe_move_height = default_z_params.Z_SAFE_MOVE_HEIGHT
        z_max = default_z_params.TRAVEL_DISTANCE
        return Z_motion(z_motor, up_sign, motor_turns_to_mm, z_safe_move_height, z_max)
    
    def stop(self):
        self.motor_z.set_effort(0)

    def __init__(self, motor_z: EncodedMotor,
            up_sign, motor_turns_to_mm, z_safe_move_height, z_max):
        self.motor_z = motor_z
        self.turns_to_mm = motor_turns_to_mm
        
        self.stop()

        ## Z upper limit
        self.z_up = 0.0
        
        ### sign of up direction
        self.up_sign = float(math.copysign(1, up_sign))
        
        ## Z max travel
        # the z axis should always be able to reach the soil.
        # if the z lenght is reached, the z axis will stop and
        # will warn the user that it did not contact soil
        self.z_length = z_max
        
        ## makes sure that you are in the upright position
        self.homed = False
        
        self.z_safe_move_height = z_safe_move_height
   
    def get_position(self) -> float: 
        would_be_position = self.motor_z.get_position() * self.turns_to_mm
        if not self.homed:
            print("Z Axis not homed")
            print("Uncalibrated pos : ", would_be_position)
        return would_be_position - self.z_up
    
    def safe_to_move(self):
        if not self.homed:
            print("Z Axis not homed")
            return False
        delta_to_top = self.z_up - self.get_position()
        if abs(delta_to_top) > self.z_safe_move_height:
            print("Z Axis not up enough to move XY")
            print("Moving could break the z axis")
            return False
        return True
   
    async def bang(self, z_effort:float):
        ### bang the z axis until stall
        
        # save initial encoder positions
        startingZ = self.motor_z.get_position()
        
        ### Let the gantry move
        self.motor_z.set_effort(z_effort)
        await asyncio.sleep_ms(500) 
        
        ### Go until stall
        while math.fabs(self.motor_z.speed) > 1:
            await asyncio.sleep_ms(10) 

 
        ### Stop the axis
        self.motor_z.set_effort(0)

    async def home(self, home_effort=.7):
        await self.bang(abs(home_effort) * self.up_sign)
        self.z_up = z_up_pos = self.motor_z.get_position() * self.turns_to_mm
        self.homed = True
     
    async def down(self, effort = 1):
        await self.bang(effort * -self.up_sign)
        
    async def up(self, effort = 1):
        await self.bang(effort * self.up_sign)
        
    def check_throw(self, check_effort=1):
        print("Homing Z Up")
        self.home()
        print("Homed")
        self.down(check_effort)
        print("Z Axis bottomed at: ", self.get_position())
        

async def manual_control(z_axis):
    while True:
        
        if z_axis.motor_z.get_effort() == 0:
            command = input("Enter command: ")

            if command == "exit":
                break
            elif command == "home":
                await z_axis.home()
            elif command == "check":
                await z_axis.check_throw()
            elif command == "up":
                await z_axis.up()
            elif command == "down":
                await z_axis.down()
            elif command == "position":
                print(z_axis.get_position())
            else:
                print("Invalid command")
            

            await asyncio.sleep(.1)

async def main():
    print("Starting")
    z_axis = Z_motion.get_default_z()

    t1 = asyncio.create_task(manual_control(z_axis))
    await asyncio.gather(t1)

if __name__ == "__main__":
    print("Starting")

    asyncio.run(main())





    