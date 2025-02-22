from XRPLib.encoded_motor import EncodedMotor
from XRPLib.pid import PID
from XRPLib.timeout import Timeout
import time
import math
import uasyncio as asyncio

def bound_effort(value, max_effort=1.0):
        return max(0, min(max_effort, value))

class default_gantry_params:
    MOTOR_REDUCTION = (9/24) * (9/27) # in / out
    PULLEY_TEETH = 36 # tooth
    PULLEY_PITCH = 2 # mm
    TURNS_TO_MM = MOTOR_REDUCTION * (PULLEY_TEETH * PULLEY_PITCH)

class XY_motion:
    @classmethod
    def get_default_xy(cls, x = None, y = None):
        encMotor1 = EncodedMotor.get_default_encoded_motor(1)
        encMotor2 = EncodedMotor.get_default_encoded_motor(2)

        # Set the motors to zero effort
        encMotor1.set_effort(0)
        encMotor2.set_effort(0)

        xy_default = XY_motion(encMotor1, encMotor2, x, y,
                        default_gantry_params.TURNS_TO_MM)
        return xy_default

    def stop(self):
        self.motor_a.set_effort(0)
        self.motor_b.set_effort(0)

    def __init__(self, motor_a: EncodedMotor, motor_b: EncodedMotor,
                 x_max = None, y_max = None,
                 motor_turns_to_mm: float=default_gantry_params.TURNS_TO_MM):
        self.zero_zero = (motor_a.get_position(), motor_b.get_position())
        self.motor_a = motor_a
        self.motor_b = motor_b
        self.turns_to_mm = motor_turns_to_mm

        self.x_max = x_max
        self.y_max = y_max

        self.homed = False

        self.stop()

        # Motor A positive effort is -x +y movement
        # Motor B positive effort is -x -y movement

    def safe_to_move(self):
        safe = True
        if self.x_max is None or self.y_max is None:
            print("!!!WARNING!!! : Bounds not set, run gantry.find_size() before moving the gantry.")
            print("    hint : To skip this step in the future instantiate the Gantry object with x_max and y_max")
            safe = False
        if not self.homed:
            print("gantry must be homed before movement")
            safe = False
        return safe

    def get_position(self):
        # Returns the current position of the gantry (in cm)

        # Calculate the distance traveled in a and b
        a_motor_position = self.motor_a.get_position()
        b_motor_position = self.motor_b.get_position()

        a = (a_motor_position - self.zero_zero[0]) * self.turns_to_mm
        b = (b_motor_position - self.zero_zero[1]) * self.turns_to_mm

        # Convert to x and y
        return self.ab_to_xy(a, b)

    def xy_to_ab(self, x, y):
        # Converts from an x and y coordinates (in mm)
        # to a and b coordinates (in mm)
        if not self.homed:
            print("gantry must be homed to do this conversion")
        a = +y-x
        b = -y-x
        return (a,b)

    def ab_to_xy(self, a, b):
        # Converts from an a and b coordinates (in mm)
        # to x and y coordinates (in mm)
        if not self.homed:
            print("gantry must be homed to do this conversion")
        x = (-a-b)/2
        y = (+a-b)/2
        return (x,y)

    async def move_to(self, x_goto, y_goto, check_safety = True):
        print(f"Moving to {(x_goto, y_goto)}")
        if check_safety and not self.safe_to_move():
            return
        x_at, y_at = self.get_position()
        await self.move_relative_xy(x_goto - x_at, y_goto - y_at)
        print(f"Moved to {(x_goto, y_goto)}")

    async def move_relative_xy(self,
                x:float,
                y:float,
                base_effort:float=0.8,
                kp:float=10,
                check_safety = True):
        if check_safety and not self.safe_to_move():
            return

        ## check if gantry would leave bounds
        x_at, y_at = self.get_position()
        x_final = x + x_at
        y_final = y + y_at
        if x_final > self.x_max or x_final < 0 or y_final > self.y_max or y_final < 0:
            print("Gantry would leave bounds, not moving")
            return

        relative_a_mm, relative_b_mm = self.xy_to_ab(x, y)
        relative_a_turns = relative_a_mm / self.turns_to_mm
        relative_b_turns = relative_b_mm / self.turns_to_mm
        print(f"Moving {x} in x and {y} in y. Traveling from {self.get_position()} to {(x,y)}")
        print(f"Relative a: {relative_a_mm} and b: {relative_b_mm}")
        await self.move_relative_ab(relative_a_turns, relative_b_turns, base_effort, kp, check_safety=check_safety)

    async def move_relative_ab(self,
               delta_a:float, # turns
               delta_b:float, # turns
               base_effort:float=0.8,
               kp:float=10,
               proximity_distance=5, # mm
               slow_down_distance=10, # mm
               slow_down_effort=0.5,
               check_safety = True):

        print("Moving Reletive")

        if check_safety and not self.safe_to_move():
            return
        startingA = self.motor_a.get_position()
        startingB = self.motor_b.get_position()

        targetA = startingA + delta_a
        targetB = startingB + delta_b

        encoderCorrection_max = 1 - base_effort
        peak_effort = 1.0

        # counter = 0

        while(True):
            x, y = self.get_position()

            total_mm_diff = math.fabs(targetA - self.motor_a.get_position()) + math.fabs(targetB - self.motor_b.get_position()) * self.turns_to_mm
            if total_mm_diff < proximity_distance:
                ### if within 5 mm of target of sum belt length diff, exit
                break
            elif total_mm_diff < slow_down_distance:
                ### if within 50 mm of target of sum belt length diff, slow down
                peak_effort = slow_down_effort

            delta_a_so_far = self.motor_a.get_position() - startingA
            delta_a_to_done = targetA - self.motor_a.get_position()
            if delta_a_to_done == 0 or delta_a == 0:
                a_fraction_done = 1
            else:
                a_fraction_done = delta_a_so_far / delta_a

            delta_b_so_far = self.motor_b.get_position() - startingB
            delta_b_to_done = targetB - self.motor_b.get_position()
            if delta_b_to_done == 0 or delta_b == 0:
                b_fraction_done = 1
            else:
                b_fraction_done = delta_b_so_far / delta_b

            encoderCorrection = kp*(a_fraction_done - b_fraction_done)

            if not delta_a_to_done:
                delta_a_to_done = 1

            a_effort = bound_effort(base_effort - encoderCorrection, peak_effort) * math.copysign(1, delta_a_to_done)
            b_effort = bound_effort(base_effort + encoderCorrection, peak_effort) * math.copysign(1, delta_b_to_done)

            self.motor_a.set_effort(a_effort)
            self.motor_b.set_effort(b_effort)
            await asyncio.sleep(0.1)

        self.motor_a.set_effort(0)
        self.motor_b.set_effort(0)

    async def bang(self,
             A_Motor_Direction = 1,
             B_Motor_Direction = 1,
             base_effort = 0.5,
             kp = .2):
        ### bangs the gantry into the endstop
        # A_Motor_Direction: A bias sign
        # B_Motor_Direction: B bias sign
        # base_effort: base effort for the motors
        # kp: proportional gain for the motors

        # save initial encoder positions
        startingA = self.motor_a.get_position()
        startingB = self.motor_b.get_position()

        encoderCorrection_max = 1 - base_effort

        ### Let the gantry move
        self.motor_a.set_effort(A_Motor_Direction*base_effort)
        self.motor_b.set_effort(B_Motor_Direction*base_effort)
        await asyncio.sleep(0.5)

        while True:
            deltaA = self.motor_a.get_position() - startingA
            deltaB = self.motor_b.get_position() - startingB
            encoderCorrection = kp*(abs(deltaA) - abs(deltaB))

            self.motor_a.set_effort(A_Motor_Direction*(bound_effort(base_effort - encoderCorrection)))
            self.motor_b.set_effort(B_Motor_Direction*(bound_effort(base_effort + encoderCorrection)))

            # not moving ?
            if math.fabs(self.motor_a.speed) <= 5 and math.fabs(self.motor_b.speed) <= 5:
                self.motor_a.set_effort(0)
                self.motor_b.set_effort(0)
                break


        self.motor_a.set_effort(0)
        self.motor_b.set_effort(0)

    async def home(self):
        print("Homing Gantry")
        await self.bang(1, 1, 0.9, 0.2)
        print("-X Bang")
        await self.bang(-1, 1, 0.9, 0.2)
        print("-Y Bang")
        self.zero_zero = (self.motor_a.get_position(), self.motor_b.get_position())
        self.homed = True

    async def find_size(self):
        if not self.homed:
            print("gantry must be homed before finding size")
            return
        # Moves the gantry to the maximum x and y coordinates
        # and returns the size of the gantry in cm
        await self.bang(-1, -1, 0.9, 0.2)
        print("+X Bang")
        await self.bang(1, -1, 0.9, 0.2)
        print("+Y Bang")
        self.x_max, self.y_max = self.get_position()

        print("I'm at ", self.get_position())
        print("Bounds Found & Logged")
        print("X Max: ", self.x_max)
        print("Y Max: ", self.y_max)

        return self.x_max, self.y_max


async def manual_control(gantry):
    while True:
        if gantry.motor_a.get_effort() == 0 and gantry.motor_b.get_effort() == 0:
            command = input("Enter command: ")

            if command == "exit":
                break
            elif command == "home":
                await gantry.home()
            elif command == "find_size":
                await gantry.find_size()
            elif command == "move":
                x = float(input("Enter x: "))
                y = float(input("Enter y: "))
                await gantry.move_to(x, y)
            elif command == "position":
                print(gantry.get_position())
            else:
                print("Invalid command")
            await asyncio.sleep(.1)

# Run both tasks.
async def main():
    gantry = XY_motion.get_default_xy(200, 200)

    t1 = asyncio.create_task(manual_control(gantry))
    await asyncio.gather(t1)

if __name__ == "__main__":
    asyncio.run(main())








