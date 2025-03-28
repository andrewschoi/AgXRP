# File helpers
from controller import Controller

import time
from agbot_file_util import Utils
import sys

sys.path.append("")

from micropython import const

import uasyncio as asyncio
import aioble
from bluetooth import UUID

import machine

import struct
import gc

#########################  HELPERS    #######################
def async_garbage_collect(func):
    """
    Garbage Collect Before Running [func]
    """
    async def collect_before_run(*args, **kwargs):
        gc.collect()
        result = await func(*args, **kwargs)
        return result
    return collect_before_run


def assertp(predicate, message="Something Bad Happened..."):
    """
    Check If Predicate Is True, Otherwise Raise An Exception
    Can Optionally Pass A Message
    """
    if not predicate:
        raise Exception(message)

class Interrupt(Exception):
    pass

#########################  BLUETOOTH    #######################

DEVICE_UUID = UUID(0x181A)

SENSOR_ACTUAL_LOCATION_UUID  = UUID("35f24b15-aa74-4cfb-a66a-a3252d67c264")
SENSOR_DESIRED_LOCATION_UUID = UUID("5bfd1e3d-e9e6-4272-b3fe-0be36b98fb9c")
JSON_CHARACTERISTIC_UUID   = UUID("16cbec17-9876-490c-bc71-85f24643a7d9")
JSON_WRITE_CHARACTERISTIC_UUID   = UUID("dc5d258b-ae55-48d3-8911-7c733b658cfd")

ADVERTISING_APPEARANCE = const(1366)

# How Frequently To Send Advertising Beacons.
ADVERTISING_INTERVAL_MILLISECONDS = 100

device_info_service = aioble.Service(DEVICE_UUID)

sensor_location_characteristic = aioble.Characteristic(
    device_info_service, SENSOR_ACTUAL_LOCATION_UUID, read=True, notify=True
)

sensor_desired_location_characteristic = aioble.Characteristic( 
    device_info_service, SENSOR_DESIRED_LOCATION_UUID, write=True, capture=True
)

json_characteristic = aioble.Characteristic(
    device_info_service, JSON_CHARACTERISTIC_UUID, read=True, notify=True
)

json_write_characteristic = aioble.Characteristic(
    device_info_service, JSON_WRITE_CHARACTERISTIC_UUID, write=True, capture=True
)

aioble.register_services(device_info_service)


#########################  ACTIONS    #######################
async def agbot_stop(controller):
    controller.agbot.stop()


async def agbot_move_to(controller, data):
    # Need The 3-4, 5-6 Bytes For Position
    position_bytes = data[2:6]
    x, y = struct.unpack("<HH", position_bytes)
    print("Moving to: ", x, y)
    await controller.agbot.move_to(x, y)


async def agbot_get_moisture_reading(controller):
    print("Probing...")
    moisture_reading = await controller.agbot.read()
    print("Moisture reading: ", moisture_reading)


async def agbot_go_home(controller):
    await controller.agbot.home()


async def agbot_run_mission(controller, data):
    mission_id_bytes = data[2:4]
    mission_id, = struct.unpack("<H", mission_id_bytes)
    print("Running mission: ", mission_id)
    await controller.run_mission(mission_id=mission_id)


async def agbot_recalibrate_gantry_size(controller):
    print("Recalibrating gantry size")
    await controller.setup_xy_max(force=True)
    # move to 20, 20
    await controller.agbot.move_to(20, 20)


async def agbot_delete_mission(controller, data):
    mission_id_bytes = data[2:4]
    mission_id, = struct.unpack("<H", mission_id_bytes)
    print("Deleting mission: ", mission_id)
    controller.memory.delete_mission(mission_id)


async def agbot_delete_plant(controller, data):
    plant_id_bytes = data[2:4]
    plant_id, = struct.unpack("<H", plant_id_bytes)    
    print("Deleting plant: ", plant_id)
    controller.memory.delete_plant(plant_id)


async def agbot_modify_plants_in_mission(controller, data):
    metadata_bytes = data[2:]
    metadata = struct.unpack("<HHH", metadata_bytes)
    if metadata[2]:
        print("Adding plant to mission", metadata)
        controller.memory.add_plant_to_mission(metadata[0], metadata[1])
    else:
        print("Removing plant from mission")
        controller.memory.remove_plant_from_mission(metadata[0], metadata[1])


#########################  STATE    #########################
previous_sensor_location_characteristic_value = b""
current_sensor_location_characteristic_value = b""

previous_sensor_desired_location_characteristic_value = b""
current_sensor_desired_location_characteristic_value = b""

previous_json_characteristic_value = b""
current_json_characteristic_value = b""

previous_json_write_characteristic_value = b""
current_json_write_characteristic_value = b""


#########################  HELPERS    #######################
@async_garbage_collect
async def wait_for_write(characteristic):
    """
    Waits For Write From On [characteristic]
    When A Write Is Received, Updates The Current & Previous Characteristic Value

    Example:
    - sensor_location_characteristic is written to with value 1
    -> previous_sensor_location_characteristic_value = b""
    -> current_sensor_location_characteristic_value = b"1"
    - sensor_location_characteristic is written to with value 2
    -> previous_sensor_location_characteristic_value = b"1"
    -> current_sensor_location_characteristic_value = b"2"
    """
    global previous_sensor_desired_location_characteristic_value
    global current_sensor_desired_location_characteristic_value

    global previous_sensor_location_characteristic_value
    global current_sensor_location_characteristic_value

    global previous_sensor_desired_location_characteristic_value
    global current_sensor_desired_location_characteristic_value

    global previous_json_characteristic_value
    global current_json_characteristic_value

    global previous_json_write_characteristic_value
    global current_json_write_characteristic_value

    _, value = await characteristic.written(timeout_ms=5000)

    if characteristic.uuid == SENSOR_ACTUAL_LOCATION_UUID:
        temp = current_sensor_location_characteristic_value
        current_sensor_location_characteristic_value = value
        previous_sensor_desired_location_characteristic_value = temp
    elif characteristic.uuid == SENSOR_DESIRED_LOCATION_UUID:
        temp = current_sensor_desired_location_characteristic_value
        current_sensor_desired_location_characteristic_value = value
        previous_sensor_desired_location_characteristic_value = temp
    elif characteristic.uuid == JSON_CHARACTERISTIC_UUID:
        temp = current_json_characteristic_value
        current_json_characteristic_value = value
        previous_json_characteristic_value = temp
    elif characteristic.uuid == JSON_WRITE_CHARACTERISTIC_UUID:
        temp = current_json_write_characteristic_value
        current_json_write_characteristic_value = value
        previous_json_write_characteristic_value = temp
    else:
        assertp(False, "Not A Known Characteristic")


#########################  TASKS    #########################
@async_garbage_collect
async def poll_for_new_commands(characteristic, polling_interval_milliseconds=1000):
    """
    Polls For New Writes On [characteristic]
    If A New Write Is Received And Is Different From The Value 
    Corresponding To The Current Characteristic Value Raise An Interrupt
    """
    global previous_sensor_location_characteristic_value
    global current_sensor_location_characteristic_value

    global previous_sensor_location_characteristic_value
    global current_sensor_desired_location_characteristic_value

    global previous_json_characteristic_value
    global current_json_characteristic_value

    global previous_json_write_characteristic_value
    global current_json_write_characteristic_value

    while True:
        try:
            if characteristic.uuid == SENSOR_ACTUAL_LOCATION_UUID:
                await wait_for_write(characteristic)
                if previous_sensor_location_characteristic_value != current_sensor_location_characteristic_value:
                    raise Interrupt
            elif characteristic.uuid == SENSOR_DESIRED_LOCATION_UUID:
                await wait_for_write(characteristic)
                if previous_sensor_desired_location_characteristic_value != current_sensor_desired_location_characteristic_value:
                    raise Interrupt
            elif characteristic.uuid == JSON_CHARACTERISTIC_UUID:
                await wait_for_write(characteristic)
                if previous_json_characteristic_value != current_json_characteristic_value:
                    raise Interrupt
            elif characteristic.uuid == JSON_WRITE_CHARACTERISTIC_UUID:
                await wait_for_write(characteristic)
                if previous_json_write_characteristic_value != current_json_write_characteristic_value:
                    raise Interrupt
            else:
                assertp(False, f"Not A Known Characteristic {characteristic}")
        except asyncio.TimeoutError:
            continue
        finally:
            if characteristic.uuid == SENSOR_ACTUAL_LOCATION_UUID:
                previous_sensor_location_characteristic_value = current_sensor_location_characteristic_value
            elif characteristic.uuid == SENSOR_DESIRED_LOCATION_UUID:
                previous_sensor_desired_location_characteristic_value = current_sensor_desired_location_characteristic_value
            elif characteristic.uuid == JSON_CHARACTERISTIC_UUID:
                previous_json_characteristic_value = current_json_characteristic_value
            elif characteristic.uuid == JSON_WRITE_CHARACTERISTIC_UUID:
                previous_json_write_characteristic_value = current_json_write_characteristic_value
            else:
                assertp(False, f"Not A Known Characteristic {characteristic}")
            await asyncio.sleep_ms(polling_interval_milliseconds)


# This is a task that waits for writes from the client
# and updates the sensor location.
@async_garbage_collect
async def sensor_location_task(controller):
    global current_sensor_desired_location_characteristic_value
    if not current_sensor_desired_location_characteristic_value:
        return
    """
    Action types (2 bytes uint16)
    0 -> Stop
    1 -> Move To Absolute Position
    2 -> Probe At Current Position
    3 -> Move To Home Position
    4 -> Turn On Pump Of A Certain Amount
    5 -> Run Mission By Id
        2 Bytes For Mission Id uint16
    6 -> Re-calibrate Gantry Size
    7 -> Change Mission Details By Id
    8 -> Delete Mission By Id
        2 Bytes For Mission Id uint16
    9 -> Delete Plant By Id
        2 Bytes For Plant Id uint16
    Grab The First Byte Of The Data To Determine The Action
    """

    """
    <H -> Little Endian unsigned short
    """
    action_bytes = current_sensor_desired_location_characteristic_value[:2]
    print(f"Trying To Unpack {type(action_bytes)}")
    action, = struct.unpack("<H", action_bytes)

    print("Mission action:", action)
    
    if action == 0:
        await agbot_stop(controller)
    elif action == 1:
        await agbot_move_to(controller, current_sensor_desired_location_characteristic_value)
    elif action == 2:
        await agbot_get_moisture_reading(controller)
    elif action == 3:
        await agbot_go_home(controller)
    elif action == 5:
        await agbot_run_mission(controller, current_sensor_desired_location_characteristic_value)
    elif action == 6:
        await agbot_recalibrate_gantry_size(controller)
    elif action == 8:
        await agbot_delete_mission(controller, current_sensor_desired_location_characteristic_value)
    elif action == 9:
        await agbot_delete_plant(controller, current_sensor_desired_location_characteristic_value)
    elif action == 10:
        await agbot_modify_plants_in_mission(controller, current_sensor_desired_location_characteristic_value)
    else:
        assertp(False, "Not A Known Action")
        

@async_garbage_collect
async def sensor_location_task_action_loop(controller):
    while True:
        current_sensor_location_task = None
        poll_for_new_commands_task = None
        try:
            current_sensor_location_task = asyncio.create_task(sensor_location_task(controller))
            poll_for_new_commands_task = asyncio.create_task(poll_for_new_commands(sensor_desired_location_characteristic))
            await asyncio.gather(current_sensor_location_task, poll_for_new_commands_task)
        except Interrupt as e:
            if current_sensor_location_task and not current_sensor_location_task.done():
                current_sensor_location_task.cancel()
            try:
                await current_sensor_location_task
            except asyncio.CancelledError:
                print("Sensor location task cancelled.")
            continue
        except Exception as e:
            print(e)


@async_garbage_collect
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


@async_garbage_collect
async def notify_gatt_client(connection):
   if connection is None: 
       return
   sensor_location_characteristic.notify(connection)


@async_garbage_collect
async def file_write_task(controller):
    while True:
        connection, data = await json_write_characteristic.written() # type: ignore
        print("Received json data: ", data)
        if data is not None:
            file_id_bytes = data[:1]
            file_id, = list(map(int, struct.unpack("<B", file_id_bytes)))
            
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
                """
                New plant data
                Data
                Byte 1-2 -> plant x position
                Byte 3-4 -> plant y position
                Byte 5-6 -> sensor x position
                Byte 7-8 -> sensor y position
                Byte 9 -> ml to water
                Byte 10 -> moisture threshold
                Byte 11-20 -> plant name
                """

                struct_string = "<HHHHBB" + str(len(data) - 11) + "s"
                plant_data_bytes = data[1:]
                plant_x_coordinates, plant_y_coordinates, sensor_x_position, sensor_y_position, ml_to_water, moisture_threshold, plant_name = struct.unpack(struct_string, plant_data_bytes)

                # Decode Plant Name
                plant_name = plant_name.decode("utf-8")

                plant = struct.unpack(struct_string, plant_data_bytes)
                
                print(f"Plant Data: {plant}\nX: {plant_x_coordinates}\nY: {plant_y_coordinates}\nSense X: {sensor_x_position}\nSense Y: {sensor_y_position}\nML to water: {ml_to_water}\nMoisture threshold: {moisture_threshold}\nPlant name: {plant_name}")

                controller.memory.add_plant(plant_name.rstrip(),
                                            sensor_x_position, sensor_y_position,
                                            plant_x_coordinates, plant_y_coordinates,
                                            moisture_threshold,
                                            ml_to_water)
                
                # after adding resend the farm data
                file_id_bytes = data[:1]
                file_id, = list(map(int, struct.unpack("<B", file_id_bytes)))
                for packet in Utils.send_file_task(controller.memory.data, "JSON"):
                    json_characteristic.write(packet)
                    json_characteristic.notify(connection)
                    await asyncio.sleep_ms(100)
                    
            elif file_id == 4:
                """
                New Mission Data
                Byte 1 -> Mission Id
                Byte 2 -> Hour
                Byte 3 -> Minute
                Byte 4 -> Action
                Byte 5... -> Mission Name
                """
                struct_string = "<BBB" + str(len(data) - 4) + "s"
                time_and_name_bytes = data[1:]
                hour, minute, action, name = struct.unpack(struct_string, time_and_name_bytes)
                name = name.decode("utf-8")
                print(f"Hour: {hour}\nMinute: {minute}\nAction: {action}\nMission Name: {name}")

                # Strip the mission name of any trailing spaces
                controller.memory.add_mission(name.rstrip(),
                                              hour, minute,
                                              name)
                
                # after adding resend the farm data
                file_id_bytes = data[:1]
                file_id, = list(map(int, struct.unpack("<B", file_id_bytes)))
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
                """
                Set Time Data
                Byte 1 -> Second
                Byte 2 -> Minute
                Byte 3 -> Hour
                Byte 4 -> Weekday
                Byte 5 -> Month
                Byte 6 -> Day
                Byte 7 -> Year
                """
                struct_string = "<BBBBBBB"
                time_bytes = data[1:]
                seconds, minutes, hours, weekdays, months, days, years = struct.unpack(struct_string, time_bytes)
                print("Time: ", time)
                try:
                    controller.clock.set_time_piece_by_piece(seconds, minutes, hours, weekdays, months, days, years)
                except Exception as e:
                    print("Error: %s" % e)

        await asyncio.sleep_ms(100)       


@async_garbage_collect
async def peripheral_task():
   while True:
      
      print("Advertising...")
      
      async with await aioble.advertise(
            ADVERTISING_INTERVAL_MILLISECONDS,
            name="FarmBot",
            services=[DEVICE_UUID],
            appearance=ADVERTISING_APPEARANCE,
         ) as connection: # type: ignore
      
         print("Connection from", connection.device)

         while connection.is_connected():
            await notify_gatt_client(connection)
            await asyncio.sleep(1)
   

async def tasks(controller):
    sensor_location_async_task = asyncio.create_task(sensor_location_task_action_loop(controller))
    file_write_async_task = asyncio.create_task(file_write_task(controller))
    sensor_async_task = asyncio.create_task(sensor_task(controller))
    peripheral_async_task = asyncio.create_task(peripheral_task())
    controller_async_task = asyncio.create_task(controller.run())  
    await asyncio.gather(sensor_location_async_task, file_write_async_task, sensor_async_task, peripheral_async_task, controller_async_task) # type: ignore


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