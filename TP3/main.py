import enum
import math
import random
import uuid
from enum import Enum

import mesa
import numpy as np
from collections import defaultdict

import mesa.space
from mesa import Agent, Model
from mesa.datacollection import DataCollector
from mesa.time import RandomActivation
from mesa.visualization.ModularVisualization import VisualizationElement, ModularServer
from mesa.visualization.modules import ChartModule

MAX_ITERATION = 100
PROBA_CHGT_ANGLE = 0.01


def move(x, y, speed, angle):
    return x + speed * math.cos(angle), y + speed * math.sin(angle)


def go_to(x, y, speed, dest_x, dest_y):
    if np.linalg.norm((x - dest_x, y - dest_y)) < speed:
        return dest_x, dest_y, 2 * math.pi * random.random()
    else:
        angle = math.acos((dest_x - x)/np.linalg.norm((x - dest_x, y - dest_y)))
        if dest_y < y:
            angle = - angle
        return x + speed * math.cos(angle), y + speed * math.sin(angle), angle


class MarkerPurpose(Enum):
    DANGER = enum.auto(),
    INDICATION = enum.auto()


class ContinuousCanvas(VisualizationElement):
    local_includes = [
        "./js/simple_continuous_canvas.js",
    ]

    def __init__(self, canvas_height=500,
                 canvas_width=500, instantiate=True):
        VisualizationElement.__init__(self)
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
                portrayal["x"] = ((obj.x - model.space.x_min) /
                                  (model.space.x_max - model.space.x_min))
                portrayal["y"] = ((obj.y - model.space.y_min) /
                                  (model.space.y_max - model.space.y_min))
            representation[portrayal["Layer"]].append(portrayal)
        for obj in model.mines:
            portrayal = self.portrayal_method(obj)
            if portrayal:
                portrayal["x"] = ((obj.x - model.space.x_min) /
                                  (model.space.x_max - model.space.x_min))
                portrayal["y"] = ((obj.y - model.space.y_min) /
                                  (model.space.y_max - model.space.y_min))
            representation[portrayal["Layer"]].append(portrayal)
        for obj in model.markers:
            portrayal = self.portrayal_method(obj)
            if portrayal:
                portrayal["x"] = ((obj.x - model.space.x_min) /
                                  (model.space.x_max - model.space.x_min))
                portrayal["y"] = ((obj.y - model.space.y_min) /
                                  (model.space.y_max - model.space.y_min))
            representation[portrayal["Layer"]].append(portrayal)
        for obj in model.obstacles:
            portrayal = self.portrayal_method(obj)
            if portrayal:
                portrayal["x"] = ((obj.x - model.space.x_min) /
                                  (model.space.x_max - model.space.x_min))
                portrayal["y"] = ((obj.y - model.space.y_min) /
                                  (model.space.y_max - model.space.y_min))
            representation[portrayal["Layer"]].append(portrayal)
        for obj in model.quicksands:
            portrayal = self.portrayal_method(obj)
            if portrayal:
                portrayal["x"] = ((obj.x - model.space.x_min) /
                                  (model.space.x_max - model.space.x_min))
                portrayal["y"] = ((obj.y - model.space.y_min) /
                                  (model.space.y_max - model.space.y_min))
            representation[portrayal["Layer"]].append(portrayal)
        return representation


class Obstacle:  # Environnement: obstacle infranchissable
    def __init__(self, x, y, r):
        self.x = x
        self.y = y
        self.r = r

    def portrayal_method(self):
        portrayal = {"Shape": "circle",
                     "Filled": "true",
                     "Layer": 1,
                     "Color": "black",
                     "r": self.r}
        return portrayal


class Quicksand:  # Environnement: ralentissement
    def __init__(self, x, y, r):
        self.x = x
        self.y = y
        self.r = r

    def portrayal_method(self):
        portrayal = {"Shape": "circle",
                     "Filled": "true",
                     "Layer": 1,
                     "Color": "olive",
                     "r": self.r}
        return portrayal


class Mine:  # Environnement: élément à ramasser
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def portrayal_method(self):
        portrayal = {"Shape": "circle",
                     "Filled": "true",
                     "Layer": 2,
                     "Color": "black",
                     "r": 2}
        return portrayal


class Marker:  # La classe pour les balises
    def __init__(self, x, y, purpose, direction=None):
        self.x = x
        self.y = y
        self.purpose = purpose
        if purpose == MarkerPurpose.INDICATION:
            if direction is not None:
                self.direction = direction
            else:
                raise ValueError("Direction should not be none for indication marker")

    def portrayal_method(self):
        portrayal = {"Shape": "circle",
                     "Filled": "true",
                     "Layer": 2,
                     "Color": "red" if self.purpose == MarkerPurpose.DANGER else "green",
                     "r": 2}
        return portrayal


class Robot(Agent):  # La classe des agents
    def __init__(self, unique_id: int, model: Model, x, y, speed, sight_distance, angle=0.0):
        super().__init__(unique_id, model)
        self.x = x
        self.y = y
        self.speed = speed
        self.speed_initial = speed
        self.sight_distance = sight_distance
        self.angle = angle
        self.counter = 0
        self.mine = None
        self.marker = None
        self.x_next = 0
        self.y_next = 0


    def collision_avoid(self):

        for robot in self.model.schedule.agents:
            if robot is not self:
                if np.linalg.norm((self.x_next - robot.x, self.y_next - robot.y)) < self.speed_initial:
                    return True

        for obstacle in self.model.obstacles:
            if np.linalg.norm((self.x_next - obstacle.x, self.y_next - obstacle.y)) < obstacle.r:
                return True

        if self.x_next > self.model.space.x_max or self.x_next < self.model.space.x_min:
            return True

        elif self.y_next > self.model.space.y_max or self.y_next < self.model.space.y_min:
            return True

        else:
            return False


    def step(self):
        # TODO L'intégralité du code du TP peut être ajoutée ici.

        speed1 = self.speed
        self.speed = self.speed_initial

        # if in a quick sand then speed is half
        for quicksand in self.model.quicksands:
            if np.linalg.norm((self.x - quicksand.x, self.y - quicksand.y)) < quicksand.r:
                self.speed = self.speed_initial / 2
                self.model.time_quicksand += 1

        # when leave the quicksand
        if speed1 == self.speed_initial / 2 and self.speed == self.speed_initial:
            self.model.markers.append(Marker(self.x, self.y, MarkerPurpose.DANGER))
            self.counter = int(self.speed_initial / 2)

        # when not moving towards a mine, just wandering
        if self.mine is None:
            if random.random() < PROBA_CHGT_ANGLE:
                self.angle = 2 * math.pi * random.random()
            self.x_next, self.y_next = move(self.x, self.y, self.speed, self.angle)

        if self.mine is not None:
            # arrive at the mine
            if self.x == self.mine.x and self.y == self.mine.y:

                self.x_next, self.y_next = move(self.x, self.y, self.speed, self.angle)

                for mine1 in self.model.mines:
                    if self.mine == mine1:
                        self.model.mines.remove(self.mine)

                self.mine = None

                # set the DANGER marker
                self.model.markers.append(Marker(self.x, self.y, MarkerPurpose.INDICATION, self.angle))
                self.counter = int(self.speed_initial / 2)

            # moving towards the mine
            else:
                self.x_next, self.y_next, self.angle = go_to(self.x, self.y, self.speed, self.mine.x, self.mine.y)

        # look for a target mine
        if self.mine is None:
            for mine in self.model.mines:
                if np.linalg.norm((self.x - mine.x, self.y - mine.y)) < self.sight_distance:
                    self.mine = mine
                    self.x_next, self.y_next, self.angle = go_to(self.x, self.y, self.speed, self.mine.x, self.mine.y)
                    self.marker = None
                    break

        # look for a marker
        if self.marker is None:
            if self.counter == 0:
                for marker in self.model.markers:
                    if np.linalg.norm((self.x - marker.x, self.y - marker.y)) < self.sight_distance:
                        self.marker = marker
                        break

        if self.marker is not None and self.mine is None:
            # if arrive at the marker
            if self.x == self.marker.x and self.y == self.marker.y:

                if self.marker.purpose == MarkerPurpose.INDICATION:
                    self.angle = self.marker.direction + (float(random.random() < 0.5) - 0.5) * math.pi

                elif self.marker.purpose == MarkerPurpose.DANGER:
                    self.angle += math.pi

                for marker1 in self.model.markers:
                    if self.marker == marker1:
                        self.model.markers.remove(self.marker)
                self.marker = None

            # moving towards the marker
            else:
                self.x_next, self.y_next, self.angle = go_to(self.x, self.y, self.speed, self.marker.x, self.marker.y)


        while(self.collision_avoid()):
            self.angle = 2 * math.pi * random.random()
            self.x_next, self.y_next = move(self.x, self.y, self.speed, self.angle)

        self.x = self.x_next
        self.y = self.y_next

        if not self.counter == 0:
            self.counter -= 1






    def portrayal_method(self):
        portrayal = {"Shape": "arrowHead", "s": 1, "Filled": "true", "Color": "Red", "Layer": 3, 'x': self.x,
                     'y': self.y, "angle": self.angle}
        return portrayal


class MinedZone(Model):
    collector = DataCollector(
        model_reporters={"Mines": lambda model: len(model.mines),
                         "Destroyed mines": lambda model: model.mines_initial - len(model.mines),
                         "Danger markers": lambda model: len([m for m in model.markers if
                                                          m.purpose == MarkerPurpose.DANGER]),
                         "Indication markers": lambda model: len([m for m in model.markers if
                                                          m.purpose == MarkerPurpose.INDICATION]),
                         "Time in quicksand": lambda model: model.time_quicksand,
                         },
        agent_reporters={})

    def __init__(self, n_robots, n_obstacles, n_quicksand, n_mines, speed):
        Model.__init__(self)
        self.space = mesa.space.ContinuousSpace(600, 600, False)
        self.schedule = RandomActivation(self)
        self.mines = []  # Access list of mines from robot through self.model.mines
        self.markers = []  # Access list of markers from robot through self.model.markers (both read and write)
        self.obstacles = []  # Access list of obstacles from robot through self.model.obstacles
        self.quicksands = []  # Access list of quicksands from robot through self.model.quicksands

        self.mines_initial = n_mines
        self.time_quicksand = 0

        for _ in range(n_obstacles):
            self.obstacles.append(Obstacle(random.random() * 500, random.random() * 500, 10 + 20 * random.random()))
        for _ in range(n_quicksand):
            self.quicksands.append(Quicksand(random.random() * 500, random.random() * 500, 10 + 20 * random.random()))
        for _ in range(n_robots):
            x, y = random.random() * 500, random.random() * 500
            while [o for o in self.obstacles if np.linalg.norm((o.x - x, o.y - y)) < o.r] or \
                    [o for o in self.quicksands if np.linalg.norm((o.x - x, o.y - y)) < o.r]:
                x, y = random.random() * 500, random.random() * 500
            self.schedule.add(
                Robot(int(uuid.uuid1()), self, x, y, speed,
                      2 * speed, random.random() * 2 * math.pi))
        for _ in range(n_mines):
            x, y = random.random() * 500, random.random() * 500
            while [o for o in self.obstacles if np.linalg.norm((o.x - x, o.y - y)) < o.r] or \
                    [o for o in self.quicksands if np.linalg.norm((o.x - x, o.y - y)) < o.r]:
                x, y = random.random() * 500, random.random() * 500
            self.mines.append(Mine(x, y))
        self.datacollector = self.collector

    def step(self):
        self.datacollector.collect(self)
        self.schedule.step()
        if not self.mines:
            self.running = False


def run_single_server():
    chart = ChartModule([{"Label": "Mines",
                          "Color": "Orange"},
                         {"Label": "Destroyed mines",
                          "Color": "Black"},
                         {"Label": "Danger markers",
                          "Color": "Red"},
                         {"Label": "Indication markers",
                          "Color": "Green"},
                         {"Label": "Time in quicksand",
                          "Color": "Blue"}
                         ],
                        data_collector_name='datacollector')
    server = ModularServer(MinedZone,
                           [ContinuousCanvas(),
                            chart],
                           "Deminer robots",
                           {"n_robots": mesa.visualization.
                            ModularVisualization.UserSettableParameter('slider', "Number of robots", 7, 3,
                                                                       15, 1),
                            "n_obstacles": mesa.visualization.
                            ModularVisualization.UserSettableParameter('slider', "Number of obstacles", 5, 2, 10, 1),
                            "n_quicksand": mesa.visualization.
                            ModularVisualization.UserSettableParameter('slider', "Number of quicksand", 5, 2, 10, 1),
                            "speed": mesa.visualization.
                            ModularVisualization.UserSettableParameter('slider', "Robot speed", 15, 5, 40, 5),
                            "n_mines": mesa.visualization.
                            ModularVisualization.UserSettableParameter('slider', "Number of mines", 15, 5, 30, 1)})
    server.port = 8521
    server.launch()


if __name__ == "__main__":
    run_single_server()
