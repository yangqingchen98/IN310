import math
import random
import numpy as np
from collections import defaultdict

import uuid
import mesa
import numpy as np
import pandas
from mesa import space
from mesa.batchrunner import BatchRunner
from mesa.datacollection import DataCollector
from mesa.time import RandomActivation
from mesa.visualization.ModularVisualization import ModularServer, VisualizationElement
from mesa.visualization.modules import ChartModule

class ContinuousCanvas(VisualizationElement):
    local_includes = [
        "./js/simple_continuous_canvas.js",
    ]

    def __init__(self, canvas_height=500,
                 canvas_width=500, instantiate=True):
        self.canvas_height = canvas_height
        self.canvas_width = canvas_width
        self.identifier = "space-canvas"
        if (instantiate):
            new_element = ("new Simple_Continuous_Module({}, {},'{}')".
                           format(self.canvas_width, self.canvas_height, self.identifier))
            self.js_code = "elements.push(" + new_element + ");"

    def portrayal_method(self, obj):
        return obj.portrayal_method()

    def render(self, model):
        representation = defaultdict(list)
        for obj in model.schedule.agents:
            portrayal = self.portrayal_method(obj)
            if portrayal:
                portrayal["x"] = ((obj.pos[0] - model.space.x_min) /
                                  (model.space.x_max - model.space.x_min))
                portrayal["y"] = ((obj.pos[1] - model.space.y_min) /
                                  (model.space.y_max - model.space.y_min))
            representation[portrayal["Layer"]].append(portrayal)
        return representation

def wander(x, y, speed, model):
    r = random.random() * math.pi * 2
    new_x = max(min(x + math.cos(r) * speed, model.space.x_max), model.space.x_min)
    new_y = max(min(y + math.sin(r) * speed, model.space.y_max), model.space.y_min)

    return new_x, new_y


def num_population(m):
    i = 0
    for agents in m.schedule.agents:
        if agents.agent_class == None:
            i += 1
    return i

def num_persons(m):
    i = 0
    for agents in m.schedule.agents:
        if agents.agent_class == None:
            if not agents.loup:
                i += 1
    return i

def num_loups(m):
    i = 0
    for agents in m.schedule.agents:
        if agents.agent_class == None:
            if agents.loup:
                i += 1
    return i

def num_loups_transform(m):
    i = 0
    for agents in m.schedule.agents:
        if agents.agent_class == None:
            if agents.loup:
                if agents.transform:
                    i += 1
    return i



class  Village(mesa.Model):
    def  __init__(self,  n_villagers, n_loup, n_cleric, n_hunter):
        mesa.Model.__init__(self)
        self.space = mesa.space.ContinuousSpace(600, 600, False)
        self.schedule = RandomActivation(self)

        self.dc = DataCollector(model_reporters={"num_population": lambda m: num_population(m),
                                                 "num_persons": lambda m: num_persons(m),
                                                 "num_loups": lambda m: num_loups(m),
                                                 "num_loups_transform": lambda m: num_loups_transform(m)})

        for  _  in  range(n_villagers):
            self.schedule.add(Villager(random.random()  *  600,  random.random()  *  600,  10, uuid.uuid1(), self))
        for  _  in  range(n_loup):
            self.schedule.add(Villager(random.random()  *  600,  random.random()  *  600,  10, uuid.uuid1(), self, loup=True ))
        for  _  in  range(n_cleric):
            self.schedule.add(Villager(random.random()  *  600,  random.random()  *  600,  10, uuid.uuid1(), self, agent_class="Cleric"))
        for  _  in  range(n_hunter):
            self.schedule.add(Villager(random.random()  *  600,  random.random()  *  600,  10, uuid.uuid1(), self, agent_class="Hunter"))



    def step(self):
        self.schedule.step()
        self.dc.collect(self)
        if self.schedule.steps >= 1000:
            self.running = False

class Villager(mesa.Agent):
    def __init__(self, x, y, speed, unique_id: int, model: Village, distance_attack=40, p_attack=0.6, loup = False, transform = False, agent_class = None, distance_cleric=30, distance_hunt = 40):
        super().__init__(unique_id, model)
        self.pos = (x, y)
        self.speed = speed
        self.model = model
        self.distance_attack = distance_attack
        self.p_attack = p_attack
        self.loup = loup
        self.transform = transform
        self.agent_class = agent_class
        self.distance_cleric = distance_cleric
        self.distance_hunt = distance_hunt


    def portrayal_method(self):

        if self.agent_class == "Cleric":
            color = "green"
            r = 3

        elif self.agent_class == "Hunter":
            color = "black"
            r = 3

        else:
            if self.loup:
                color = "red"
                if self.transform:
                    r = 6
                else:
                    r = 3

            else:
                color = "blue"
                r = 3



        portrayal = {"Shape": "circle",
                     "Filled": "true",
                     "Layer": 1,
                     "Color": color,
                     "r": r}
        return portrayal

    def list_near_agents(self, agents, distance):

        list_near_agents = []

        for obj in agents:
            if np.square(obj.pos[0] - self.pos[0]) + np.square(obj.pos[1] - self.pos[1]) < np.square(distance):
                list_near_agents.append(obj)

        return list_near_agents


    def step(self):

        self.pos = wander(self.pos[0], self.pos[1], self.speed, self.model)

        if self.agent_class == "Cleric":

            list_near_agents = self.list_near_agents(self.model.schedule.agents, self.distance_cleric)

            for obj in list_near_agents:
                if obj.loup and not obj.transform:
                    obj.loup = False

        if self.agent_class == "Hunter":

            list_near_agents = self.list_near_agents(self.model.schedule.agents, self.distance_hunt)

            for obj in list_near_agents:
                if obj.transform:
                    if np.random.random() < self.p_attack:
                        self.model.schedule.remove(obj)

        else:

            if self.loup and np.random.random() < 0.1:
                self.transform = True

            if self.loup:
                if self.transform:
                    list_near_agents = self.list_near_agents(self.model.schedule.agents, self.distance_attack)

                    for obj in list_near_agents:
                        if np.random.random():
                            obj.loup = True




def run_single_server():

    slider_villagers = mesa.visualization.ModularVisualization.UserSettableParameter('slider', "slider_villagers", 50,
                                                                                     0, 50, 1)

    slider_clerics = mesa.visualization.ModularVisualization.UserSettableParameter('slider', "slider_clerics", 1, 0,
                                                                                   20, 1)

    slider_hunters = mesa.visualization.ModularVisualization.UserSettableParameter('slider', "slider_hunters", 2, 0,
                                                                                   20, 1)

    slider_loups = mesa.visualization.ModularVisualization.UserSettableParameter('slider', "slider_loups", 5, 0, 10, 1)

    server = ModularServer(Village, [ContinuousCanvas(), ChartModule([{"Label": "num_population", "Color": "Green"},
                                                                      {"Label": "num_persons", "Color": "Blue"},
                                                                      {"Label": "num_loups", "Color": "Orange"},
                                                                      {"Label": "num_loups_transform", "Color": "Red"}],
                                                                     data_collector_name='dc')],
                           "Village",
                           {"n_villagers": slider_villagers, "n_loup": slider_loups, "n_cleric": slider_clerics,
                            "n_hunter": slider_hunters})
    server.port = 8521
    server.launch()


def run_batch():

    model_reporters = {"num_population": lambda m: num_population(m),
                       "num_persons": lambda m: num_persons(m),
                       "num_loups": lambda m: num_loups(m),
                       "num_loups_transform": lambda m: num_loups_transform(m)}

    params_dict = {"n_villagers": [50], "n_loup": [5], "n_cleric": range(0, 6),
                            "n_hunter": [1]}


    batchrunner = BatchRunner(Village, params_dict, model_reporters=model_reporters)

    batchrunner.run_all()




if  __name__  ==  "__main__":
    #run_batch()
    run_single_server()