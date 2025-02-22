import uasyncio as asyncio
import aioble
import bluetooth

import json
import struct

file_types = {
    "JSON": 0x01,
    "CSV": 0x02,
    "TBD": 0x03
}

def calcule_hash(data):
    return sum(data) % 256

def serialize_csv(data):
    return bytearray(data, 'utf-8') 

def serialize_json(data):
    return bytearray(json.dumps(data), 'utf-8')

def deserialize_json(data):
    return json.loads(data)

def chunk_file(data, chunk_size):
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

def generate_header_message(num_chunks, json_data, file_type_id):
    header = bytearray()
    header.append(0x01)
    header.append(file_type_id)
    header.append(num_chunks)
    header.extend(struct.pack("<I", len(json_data)))
    header.append(calcule_hash(json_data))
    header.append(calcule_hash(header))
    return header

def generate_payload_message(file_chunk, chunk_index):
    payload = bytearray()
    payload.append(0x02)
    payload.append(chunk_index)
    payload.extend(file_chunk)
    payload.append(calcule_hash(payload))
    return payload

def generate_last_message(file_name=None):
    last = bytearray()
    last.append(0x03)
    if file_name is None:
        return last
    # name of file as a byte array
    last.extend(bytearray(file_name, 'utf-8'))
    return last

class Utils:
    @staticmethod
    def reading_name_from_time(month, day, year, hour, minute, second):
        return str(month) + "," + str(day) + "," + str(year-2000) + "," + str(hour) + "," + str(minute)

    @staticmethod
    def get_mission_history():
        try:
            with open("mission_history.csv", 'r') as file:
                # Return the data as a list of lists
                # each line is a mission
                # [2, 3, 4, 5]
                # where data[0] is the mission id
                # and data[1] is the day
                # and data[2] is the month
                # and data[3] is the year
                # and data[4] is the hour
                # and data[5] is the minute
                return [[int(x) for x in line.rstrip().split(",")] for line in file.readlines()]
        except Exception as e:
            print("Error reading file: ", e)
            return []

    @staticmethod
    def append_mission_to_history(mission_id, day, month, year, hour, minute):
        try:
            with open("mission_history.csv", 'a') as file:
                file.write(str(mission_id) + "," + str(day) + "," + str(month) + "," + str(year-2000) + "," + str(hour) + "," + str(minute))
                file.write('\n')
        except Exception as e:
            print("Error writing to file: ", e)

    @staticmethod
    def append_error_to_log(error):
        try:
            with open("error_log.csv", 'a') as file:
                file.write(error)
                file.write('\n')
        except Exception as e:
            print("Error writing to file: ", e)

    @staticmethod
    def get_file_data(file_name):
        try:
            with open(file_name, 'rb') as file:
                return file.read()
        except Exception as e:
            print("Error reading file: ", e)
            return None
        
    @staticmethod
    def append_reading_to_csv(file_name, reading):
        # Append the reading to the csv file
        try:
            with open(file_name, 'a') as file:
                file.write(reading)
                file.write('\n')
        except Exception as e:
            print("Error writing to file: ", e)

    # This fuction is a generator that splits the data into chunks of size n
    def send_file_task(file_data, file_type, file_name=None):
        """
        Send file data to the client in chunks
        Each chuck is X number of bytes long
        first chuck has a header of 0x01
        A payload chuck has a header of 0x02
        The last chuck has a header of 0x03

        The first chuck contains:
        - Header (0x01) - 1 byte
        - File Type - 1 byte
        -      0x01 - JSON
        -      0x02 - CSV
        -      0x03 - TBD
        - The number of chucks to be sent - 1 byte (so max 255 chucks can be sent)
        - The length of the file data - 4 bytes
        - JSON checksum - 1 byte
        - Checksum - 1 byte

        The payload chuck contains:
        - Header (0x02) - 1 byte
        - Chunk index - 1 byte
        - Checksum - 1 byte
        - file data - X bytes
                        
        The last chuck contains:
        - Header (0x03) - 1 byte
        """

        file_type_id = file_types.get(file_type, None)
        if file_type_id is None:
            print("Invalid file type", file_type_id)
            return None

        done = False
        chunk_size = 100

        # Convert file data to a byte array
        if file_type == "JSON":
            file_encoded = serialize_json(file_data)
        elif file_type == "CSV":
            file_encoded = file_data
        else:
            print("Invalid file type")
            return None

        file_chunks = chunk_file(file_encoded, chunk_size)

        header_message = generate_header_message(len(file_chunks), file_encoded, file_type_id)
        # print("Header message: ", header_message)

        yield header_message

        for index, chunk in enumerate(file_chunks):
            # print("Sent chunk: ", index, chunk)
            payload_message = generate_payload_message(chunk, index)

            yield payload_message

        last_message = generate_last_message(file_name=file_name)
        yield last_message

