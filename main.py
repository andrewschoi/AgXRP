# File helpers
from controller import Controller

import time
from agbot_file_util import Utils
import sys

sys.path.append("")

from micropython import const

import uasyncio as asyncio
import aioble
import bluetooth

import machine

import struct

# device info
_DEVICE_INFO_UUID = bluetooth.UUID(0x181A)

_ENV_SENSE_TEMP_UUID = bluetooth.UUID(0x2A6E)

_ENV_AGGREGATE_UUID = bluetooth.UUID(0x2A5A)

_ENV_SENSE_ACTUAL_LOC_UUID  = bluetooth.UUID("35f24b15-aa74-4cfb-a66a-a3252d67c264")
_ENV_SENSE_DESIRED_LOC_UUID = bluetooth.UUID("5bfd1e3d-e9e6-4272-b3fe-0be36b98fb9c")
_FILE_SEND_CHARACTERISTIC_UUID   = bluetooth.UUID("16cbec17-9876-490c-bc71-85f24643a7d9")
_FILE_WRITE_CHARACTERISTIC_UUID   = bluetooth.UUID("dc5d258b-ae55-48d3-8911-7c733b658cfd")

_ADV_APPEARANCE_GENERIC_MULTISENSOR = const(1366)

# How frequently to send advertising beacons.
_ADV_INTERVAL_MS = 100

device_info_service = aioble.Service(_DEVICE_INFO_UUID)
sensor_location_characteristic = aioble.Characteristic(
    device_info_service, _ENV_SENSE_ACTUAL_LOC_UUID, read=True, notify=True
)

sensor_desired_location_characteristic = aioble.Characteristic( 
    device_info_service, _ENV_SENSE_DESIRED_LOC_UUID, write=True, capture=True
)

temp_characteristic = aioble.Characteristic(
    device_info_service, _ENV_SENSE_TEMP_UUID, read=True, notify=True
)

json_characteristic = aioble.Characteristic(
    device_info_service, _FILE_SEND_CHARACTERISTIC_UUID, read=True, notify=True
)

json_write_characteristic = aioble.Characteristic(
    device_info_service, _FILE_WRITE_CHARACTERISTIC_UUID, write=True, capture=True
)

aioble.register_services(device_info_service)

# This is a task that waits for writes from the client
# and updates the sensor location.
async def sensor_location_task(controller):
    while True:
        connection, data = await sensor_desired_location_characteristic.written()
        print("Received desired position data: ", data)
        if data is not None:
            # Action types (2 bytes uint16)
            # 0 = Stop
            # 1 = Move to absolute position
            # 2 = probe at current position
            # 3 = Move to home position
            # 4 = Turn on pump of a certain amount
            # 5 = run mission by id
            #    - 2 bytes for mission id uint16
            # 6 = re-calibrate gantry size
            # 7 = change mission details by id
            # 8 = delete mission by id
            #    - 2 bytes for mission id uint16
            # 9 = delete plant by id
            #    - 2 bytes for plant id uint16
            # Grab the fisrt byte of the data to determine the action
            action = struct.unpack("<H", data[:2])[0]
            print("Mission action:", action)
            
            if action == 0:
                controller.agbot.stop()
            elif action == 1:
                _, x, y, _, _ = struct.unpack("<HHHHH", data)
                print("Moving to: ", x, y)
                await controller.agbot.move_to(x, y)
            elif action == 2:
                print("Probing...")
                moisture_reading = await controller.agbot.read()
                print("Moisture reading: ", moisture_reading)

            elif action == 3:
                await controller.agbot.home()
            elif action == 5:
                mission_id = struct.unpack("<H", data[2:4])[0]
                print("Running mission: ", mission_id)
                await controller.run_mission(mission_id=mission_id)
            elif action == 6:
                print("Recalibrating gantry size")
                await controller.setup_xy_max(force=True)
                # move to 20, 20
                await controller.agbot.move_to(20, 20)
            elif action == 8:
                mission_id = struct.unpack("<H", data[2:4])[0]
                print("Deleting mission: ", mission_id)
                controller.memory.delete_mission(mission_id)
            elif action == 9:
                plant_id = struct.unpack("<H", data[2:4])[0]    
                print("Deleting plant: ", plant_id)
                controller.memory.delete_plant(plant_id)
            elif action == 10:
                # add / remove plant from mission
                # 2 bytes for mission id uint16
                # 2 bytes for plant id uint16
                # 1 byte for add / remove
                #     0 = add
                #     1 = remove
                data = struct.unpack("<HHH", data[2:])
                if data[2]:
                    print("Adding plant to mission", data)
                    controller.memory.add_plant_to_mission(data[0], data[1])
                else:
                    print("Removing plant from mission")
                    controller.memory.remove_plant_from_mission(data[0], data[1])
            else:
                print("Invalid action")
            
           
        await asyncio.sleep_ms(100) 

async def sensor_task(controller):
    homed, x, y, z = 0, 0, 0, 0
    print("Sensor location task started")
    while True:
        # temp_characteristic.write(struct.pack(">H", int(t)))
        if controller.agbot.xy.homed:
            x, y = controller.agbot.xy.get_position()
            homed = 1
            z = controller.agbot.z.get_position()
            # print("X: ", x, "Y: ", y)
        else:
            homed = 0
            x, y = 0, 0
            z = 0

        sensor_location_characteristic.write(struct.pack(">HHHH", int(homed), int(x), int(y), int(z)))
        # print("sensor location data updated: ", homed, x, y, z)
        await asyncio.sleep_ms(500)

async def notify_gatt_client(connection):
   if connection is None: return
   temp_characteristic.notify(connection)
   sensor_location_characteristic.notify(connection)

async def file_write_task(controller):
    while True:
        connection, data = await json_write_characteristic.written()
        print("Received json data: ", data)
        if data is not None:
            file_id = int(struct.unpack("<B", data[:1])[0])
            if file_id == 0:
                for packet in Utils.send_file_task(controller.memory.data, "JSON"):
                    json_characteristic.write(packet)
                    json_characteristic.notify(connection)
                    await asyncio.sleep_ms(100)
            elif file_id == 1:
                pass
                # mission data
                data = Utils.get_file_data("mission_history.csv")
                if data is not None:
                    for packet in Utils.send_file_task(data, "CSV", "mission_history"):
                        json_characteristic.write(packet)
                        json_characteristic.notify(connection)
                        await asyncio.sleep_ms(100)
            elif file_id == 2:
                # Moisture data
                data = Utils.get_file_data("moisture_readings.csv")
                if data is not None:
                    for packet in Utils.send_file_task(data, "CSV", "moisture_readings"):
                        json_characteristic.write(packet)
                        json_characteristic.notify(connection)
                        await asyncio.sleep_ms(100)
            elif file_id == 3:
                # new plant data
                # data
                # byte 1-2 is the x position
                # byte 3-4 is the y position
                # byte 5-6 is the sense x position
                # byte 7-8 is the sense y position
                # byte 9 is the ml to water
                # byte 10 is the moisture threshold
                # byte 11-20 bytes is the plant name

                struct_string = "<HHHHBB" + str(len(data) - 11) + "s"

                plant = struct.unpack(struct_string, data[1:])
                print("Plant data: ", plant)
                print("X: ", plant[0])
                print("Y: ", plant[1])
                print("Sense X: ", plant[2])
                print("Sense Y: ", plant[3])
                print("ML to water: ", plant[4])
                print("Moisture threshold: ", plant[5])
                print("Plant name: ", plant[6].decode("utf-8"))

                controller.memory.add_plant(plant[6].decode("utf-8").rstrip(),
                                            plant[2], plant[3],
                                            plant[0], plant[1],
                                            plant[5],
                                            plant[4])
                
                # after adding resend the farm data
                file_id = int(struct.unpack("<B", data[:1])[0])
                for packet in Utils.send_file_task(controller.memory.data, "JSON"):
                    json_characteristic.write(packet)
                    json_characteristic.notify(connection)
                    await asyncio.sleep_ms(100)
                    
            elif file_id == 4:
                # new mission data
                # data
                # first byte is the mission id
                # 2nd byte is hour
                # 3r byte is minute
                # 4th byte is action
                # the rest is the mission name
                struct_string = "<BBB" + str(len(data) - 4) + "s"

                mission = struct.unpack(struct_string, data[1:])
                print("hour: ", mission[0])
                print("minute: ", mission[1])
                print("action: ", mission[2])
                print("Mission name: ", mission[3].decode("utf-8"))

                # Strip the mission name of any trailing spaces
                controller.memory.add_mission(mission[3].decode("utf-8").rstrip(),
                                              mission[0], mission[1],
                                              mission[2])
                
                # after adding resend the farm data
                file_id = int(struct.unpack("<B", data[:1])[0])
                for packet in Utils.send_file_task(controller.memory.data, "JSON"):
                    json_characteristic.write(packet)
                    json_characteristic.notify(connection)
                    await asyncio.sleep_ms(100)
            
            elif file_id == 5:
                # water log data
                data = Utils.get_file_data("water_log.csv")
                print("Water log data: ", data)
                if data is not None:
                    for packet in Utils.send_file_task(data, "CSV", "water_history"):
                        json_characteristic.write(packet)
                        json_characteristic.notify(connection)
                        await asyncio.sleep_ms(100)

            elif file_id == 99:
                # set time data
                # data
                # byte 1 is the second
                # byte 2 is the minute
                # byte 3 is the hour
                # byte 4 is the weekday
                # byte 5 is the month
                # byte 6 is the day
                # byte 7 is the year
                struct_string = "<BBBBBBB"
                time = struct.unpack(struct_string, data[1:])
                print("Time: ", time)
                try:
                    controller.clock.set_time_piece_by_piece(time[0], time[1], time[2], time[3], time[4], time[5], time[6])
                except Exception as e:
                    print("Error: %s" % e)

        await asyncio.sleep_ms(100)       

async def peripheral_task():
   while True:
      print("Advertising...")
      async with await aioble.advertise(
            _ADV_INTERVAL_MS,
            name="FarmBot",
            services=[_DEVICE_INFO_UUID],
            appearance=_ADV_APPEARANCE_GENERIC_MULTISENSOR,
         ) as connection:
         print("Connection from", connection.device)

         while connection.is_connected():
            await notify_gatt_client(connection)
            await asyncio.sleep(1)
   
async def tasks(controller):
    t0 = asyncio.create_task(sensor_location_task(controller))
    t1 = asyncio.create_task(file_write_task(controller))
    t2 = asyncio.create_task(sensor_task(controller))
    t3 = asyncio.create_task(peripheral_task())
    t4 = asyncio.create_task(controller.run())  
    await asyncio.gather(t0, t1, t2, t3, t4)

def main():
    try:
        controller = Controller.get_default_controller()
        asyncio.run(tasks(controller))
    except KeyboardInterrupt:
        print("Keyboard interrupt")
        controller.agbot.stop()
    except Exception as e:
        print("Error: ", e)
        controller.agbot.stop()
        Utils.append_error_to_log(str(e))
        machine.reset()
        
# Run the main function
if __name__ == "__main__":
    main()