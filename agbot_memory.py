import json
import random

from machine import RTC
from agbot_file_util import Utils


class JsonReaderWriter:
    def __init__(self, filename):
        self.filename = filename
        self.data = self.load()

    def load(self):
        with open(self.filename, 'r') as file:
            return json.load(file)

    def save(self):
        with open(self.filename, 'w') as file:
            json.dump(self.data, file)

class AgBotMemory(JsonReaderWriter):
    @classmethod
    def get_default_agbotmemory(cls):
        return AgBotMemory('/agbot_data.json')   
    
    def __init__(self, filename):
        super().__init__(filename)
    
    ### Plant Functions
    
    def add_plant(self, plant_name, 
                    x_sense : int, y_sense : int, 
                    x_plant : int, y_plant : int, 
                    moisture_threshhold: int,
                    ml_response: int):
        plant = {}
        plant['sense'] = [x_sense, y_sense]
        plant['location'] = [x_plant, y_plant]
        plant['moisture_threshhold'] = moisture_threshhold
        plant["ml_response"] = ml_response
        
        id_already_exists = False
        while True:
            plant_id = random.randint(0, 1000)
            for plant_in_mem in self.data["plants"].keys():
                if self.get_plant(plant_in_mem)['id'] == plant_id:
                    id_already_exists = True
                    print("ID already exists")
                    break
            if not id_already_exists:
                print("ID does not exist, using: ", plant_id)    
                break
    
        plant['id'] = plant_id
        
        self.data["plants"][plant_name] = plant
        self.save()

    def add_mission(self, mission_name, hour, minute, action):
        mission = {}
        mission['mission_name'] = mission_name
        mission['time'] = [hour, minute]

        if action == 0:
            mission['type'] = "water"
        elif action == 1:
            mission['type'] = "sense_moisture"

        id_already_exists = False
        while True:
            mission_id = random.randint(0, 1000)
            for mission_in_mem in self.data["missions"]:
                if mission_in_mem['mission_id'] == mission_id:
                    id_already_exists = True
                    print("ID already exists")
                    break
            if not id_already_exists:
                print("ID does not exist, using: ", mission_id)    
                break
    
        mission['mission_id'] = mission_id
        mission['locations'] = []

        self.data["missions"].append(mission)
        self.save()

    def add_plant_to_mission(self, plant_id, mission_id):
        plant = None
        # find plant name
        for plant_name in self.data["plants"].keys():
            if self.get_plant(plant_name)["id"] == plant_id:
                print("Plant found: ", plant_name)
                plant = plant_name
                break

        if plant is not None:
            # find mission
            for mission in self.data["missions"]:
                if mission['mission_id'] == mission_id:
                    print("Mission found: ", mission['mission_name'])
                    mission['locations'].append(plant)
                    self.save()
                    return

    def remove_plant_from_mission(self, plant_id, mission_id):
        plant = None
        # find plant name
        for plant_name in self.data["plants"].keys():
            if self.get_plant(plant_name)["id"] == plant_id:
                print("Plant found: ", plant_name)
                plant = plant_name
                break

        if plant is not None:
            # find mission
            for mission in self.data["missions"]:
                if mission['mission_id'] == mission_id:
                    print("Mission found: ", mission['mission_name'])
                    mission['locations'].remove(plant)
                    self.save()
                    return

    def delete_mission(self, mission_id):
        for index, mission in enumerate(self.data["missions"]):
            if mission['mission_id'] == mission_id:
                self.data["missions"].pop(index)
                self.save()
                return
      
    def delete_plant(self, plant_id):
        for plant in self.data["plants"].keys():
            print(plant)
            if self.get_plant(plant)["id"] == plant_id:
                print("Deleting plant: ", plant)
                self.data["plants"].pop(plant)
                self.save()
                return

    def get_plant(self, plant_name):
        return self.data["plants"].get(plant_name, {})

    def get_plant_names(self):
        plant_list = []
        for plant_name in self.data['plants']:
            plant_list.append(plant_name)
        return plant_list

    def get_plant_water_spot(self, plant):
        return self.get_plant(plant)['location']

    def get_plant_sense_spot(self, plant):
        return self.get_plant(plant).get('sense', None)

    def get_moisture_threshold(self, plant):
        return self.get_plant(plant)['moisture_threshhold']

    def get_plant_ml_response(self, plant):
        return self.get_plant(plant)['ml_response']
        
    def get_missions(self):
        return self.data.get("missions", [])
    
    def get_mission(self, mission_id):
        missions = self.get_missions()
        for mission in missions:
            if mission['mission_id'] == mission_id:
                return mission
        return None

    ### Gantry Params

    def get_gantry_size(self):
        return self.data['gantry_size']

    def set_gantry_size(self, x, y):
        self.data['gantry_size'] = [x,y] 
        self.save()
        
    ### Add reading to memory
    
    def does_reading_exist(self, date):
        return date in self.data['readings']
    
    def add_reading(self, plant_name, moisture_reading):
        self.data['plants']['readings'] = readings
        self.save()
        
    ### Serial Writes
    
    def manual_add_plant(self):
        plant_name = input("Enter plant name: ")
        x_sense = int(input("Enter x_sense: "))
        y_sense = int(input("Enter y_sense: "))
        x_plant = int(input("Enter x_plant: "))
        y_plant = int(input("Enter y_plant: "))
        moisture_threshhold = int(input("Enter moisture_threshhold % 0-100: "))
        ml_response = float(input("Enter water amount in 0-250: "))
        self.add_plant(plant_name, x_sense, y_sense, x_plant, y_plant, moisture_threshhold, ml_response)
        
    def manual(self):
        print("Welcome to the AG Bot Memory Manual Control")
        while True:
            print("1: Add Plant")
            print("2: List Plants")
            print("3: Get Plant Info")
            print("4: Get Gantry Size")
            print("5: Set Gantry Size")
            print("6: Exit")
            choice = int(input("Enter choice: "))
            if choice == 1:
                self.manual_add_plant()
            elif choice == 2:
                print("Plants: ")
                print(self.get_plant_names())
            elif choice == 3:
                plant_name = input("Enter plant name: ")
                print(self.get_plant(plant_name))
            elif choice == 4:
                print(self.get_gantry_size())
            elif choice == 5:
                x = float(input("Enter x: "))
                y = float(input("Enter y: "))
                self.set_gantry_size(x, y)
            elif choice == 6:
                return
            else:
                print("Invalid choice")
                

if __name__ == "__main__":
    # Example usage
    agm = AgBotMemory.get_default_agbotmemory()

    print(agm.get_gantry_size())
    for plant in agm.get_plant_names():
        print(plant, " ", agm.get_plant_water_spot(plant))

    print(agm.get_mission_time())

    time = Utils.reading_name_from_time(06, 19, 2024)
    print(time)
    print("Contains : ", time)
    # agm.save()