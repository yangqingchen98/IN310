import json  # Pour la sérialisation/désérialisation des objects
import math
import random
import string
from collections import defaultdict
from typing import List

import mesa
import mesa.space
import numpy as np
import spade  # Framework multi-agents de messages
import networkx as nx  # Pour le parcours du réseau de planètes
from mesa import Agent, Model
from threading import Lock  # Pour le mutual exclusion

from mesa.datacollection import DataCollector
from mesa.time import RandomActivation
from mesa.visualization import ModularVisualization
from mesa.visualization.ModularVisualization import VisualizationElement, ModularServer
from mesa.visualization.modules import ChartModule
from spade.behaviour import PeriodicBehaviour, OneShotBehaviour
from spade.template import Template
import uuid  # Génération de Unique ID
import re

NEW_ITEM_PROBA = 0.05
PROBA_ISSUE_ROAD = 0.05
ROAD_BRANCHING_FACTOR = 0.5
WAITING_TIME = 3


class PlanetDelivery(mesa.Model):

    def __init__(self, n_planets, n_ships):
        mesa.Model.__init__(self)
        self.space = mesa.space.ContinuousSpace(600, 600, False)
        self.schedule = RandomActivation(self)
        planets = [PlanetManager("planet-" + str(i), [], int(uuid.uuid1()), self,
                                 random.random() * 600, random.random() * 600)
                   for i in range(n_planets)]
        environment = SpaceRoadNetwork(planets, int(uuid.uuid1()), self)
        self.schedule.add(environment)
        ships = []
        for i in range(n_ships):
            starting_point = random.choice(planets)
            ship = Ship("ship-" + str(i), planets, int(uuid.uuid1()), self,
                        starting_point.x, starting_point.y, 60, environment)
            ships.append(ship)
            self.schedule.add(ship)
        for p in planets:
            p.planets = [planet for planet in planets if planet != p]
            p.ships = ships
            self.schedule.add(p)
        self.items = []
        self.computed_items_nb = 0
        self.datacollector = DataCollector(
            model_reporters={"items": lambda model: len(model.items),
                             "Delivered": lambda model: model.computed_items_nb
                             },
            agent_reporters={})

    def step(self):
        self.schedule.step()
        self.datacollector.collect(self)
        if self.schedule.steps >= 300:
            self.running = False


class Item:
    @staticmethod
    def from_json(json_object):  #Désérialisation des items pour le passage par message
        return Item(json_object['x'], json_object['y'], json_object['a'], json_object['b'], json_object['c'],
                    json_object['uid'])

    def __init__(self, x, y, a=None, b=None, c=None, uid=None):
        if not a:
            self.a = random.random()
        else:
            self.a = a
        if not b:
            self.b = random.random()
        else:
            self.b = b
        if not c:
            self.c = random.random()
        else:
            self.c = c
        self.x = x
        self.y = y
        if not uid:
            self.uid = int(uuid.uuid1())
        else:
            self.uid = uid

    def __eq__(self, other):
        return isinstance(other, Item) and self.uid == other.uid

    def __hash__(self):
        return int(self.uid)

    @staticmethod
    def portrayal_method():
        color = "yellow"
        r = 2
        portrayal = {"Shape": "circle",
                     "Filled": "true",
                     "Layer": 3,
                     "Color": color,
                     "r": r}
        return portrayal


class AgentCommunicator(spade.agent.Agent):
    def __init__(self, jid, password):
        super().__init__(jid, password)
        self.msg_box = []
        self.mutex = Lock()
        self.send_behaviour = None

    class SendBehaviour(OneShotBehaviour):
        def __init__(self, msg):
            super().__init__()
            self.msg = msg

        async def run(self):
            await self.send(self.msg)
            print("sent: " + str(self.msg) + '\n')

    class RecvBehav(PeriodicBehaviour):
        async def run(self):
            msg = await self.receive()
            if msg:
                self.agent.mutex.acquire()
                # try:
                self.agent.msg_box.append(msg)
                print("received: " + str(msg))
                # finally:
                self.agent.mutex.release()

    async def setup(self):
        b = self.RecvBehav(.01)
        self.add_behaviour(b, Template())
        print(str(self.jid) + " connected")


class CommunicatingAgent(Agent):
    def __init__(self, unique_id: int, model: Model, name: string):
        super().__init__(unique_id, model)
        self.communicator = AgentCommunicator(name + "@localhost", "password-" + name)
        self.communicator.start()

    def send(self, msg):
        self.communicator.send_behaviour = AgentCommunicator.SendBehaviour(msg)
        self.communicator.add_behaviour(self.communicator.send_behaviour)
        self.communicator.send_behaviour.join()


class Ship(CommunicatingAgent):
    def __init__(self, name: string, planets: List, unique_id: int, model: PlanetDelivery,
                 x, y, max_speed: float, environment):
        super().__init__(unique_id, model, name)
        self.preference_a = random.random()
        self.preference_b = random.random()
        self.preference_c = random.random()
        self.planets = planets
        self.x = x
        self.y = y
        self.max_speed = max_speed
        self.destination = None
        self.potential_destination = None
        self.waypoint = None
        self.previous_point = [p for p in self.planets if (p.x == self.x and p.y == self.y)][0]
        self.environment = environment
        self.item = None
        self.potential_item = None
        self.count = 0

    def move_to(self, dest, speed):
        movement = tuple(min(
            (speed * (dest.x - self.x) / np.linalg.norm((dest.x - self.x, dest.y - self.y)), speed * (dest.y - self.y) /
             np.linalg.norm((dest.x - self.x, dest.y - self.y))),
            (dest.x - self.x, dest.y - self.y), key=lambda p: np.linalg.norm(p)))
        self.x += movement[0]
        self.y += movement[1]

    def step(self):
        if self.waypoint is None and self.destination is not None:
            self.waypoint = nx.dijkstra_path(self.environment.current_graph,
                                             self.previous_point, self.destination, 'distance')[1]
        if self.waypoint is not None:
            self.move_to(self.waypoint, self.max_speed * self.environment.speed_modificator[
                (self.previous_point, self.waypoint)])
            self.item.x = self.x
            self.item.y = self.y
            if (self.x, self.y) == (self.waypoint.x, self.waypoint.y):
                self.previous_point = self.waypoint
                if self.waypoint == self.destination:
                    # deliver
                    self.waypoint = None
                    self.destination = None
                    for item in self.model.items:
                        if item.uid == self.item.uid:
                            self.model.items.remove(self.item)
                    self.destination = None
                    self.model.computed_items_nb += 1
                    self.item = None
                else:
                    self.waypoint = nx.dijkstra_path(self.environment.current_graph,
                                                     self.previous_point, self.destination,
                                                     'distance')[1]  # 0 is current planet
        self.communicator.mutex.acquire()
        try:
            messages = [m for m in self.communicator.msg_box]
            self.communicator.msg_box = []
        finally:
            self.communicator.mutex.release()

        for m in messages:
            if self.item is None and m.metadata['performative'] == "call_for_proposal" and self.potential_destination is None:  # and\

                body_split = re.split("{|}| |:|,", m.body)

                to1 = m.to
                sender1 = m.sender

                uid = float(body_split[23])
                x_dest = float(body_split[25])
                y_dest = float(body_split[26])

                self.potential_destination = [p for p in self.planets if (p.x == x_dest and p.y == y_dest)][0]

                item = None
                for p in self.model.items:
                    if p.uid - uid == 0:
                        item = p
                if item is not None:
                    utility = self.utility(item)
                    self.potential_item = item
                    proposition = spade.message.Message(to=str(sender1),
                                                        sender=str(to1),
                                                        body=str(utility),
                                                        thread='Propositions-' + str(self.communicator.jid),
                                                        metadata={"performative": "proposition",
                                                                  "turn": str(self.model.schedule.steps)})
                    self.send(proposition)

            if self.potential_item is not None:
                self.count += 1

            if self.potential_item is not None and m.metadata['performative'] == "accept_proposal":
                self.item = self.potential_item
                self.destination = self.potential_destination
                self.potential_item = None
                self.potential_destination = None
                self.count = 0

            if self.potential_item is not None and m.metadata['performative'] == "reject_proposal":
                self.potential_item = None
                self.potential_destination = None
                self.count = 0

            if self.item is not None:
                self.count += 1

            if self.count > 20:
                self.item = None
                self.destination = None
                self.potential_item = None
                self.potential_destination = None



    def utility(self, item):
        return item.a * self.preference_a + item.b * self.preference_b + item.c * self.preference_c

    def portrayal_method(self):
        portrayal = {"Shape": "arrowHead", "s": 1, "Filled": "true", "Color": "Red", "Layer": 2, 'x': self.x,
                     'y': self.y}
        if self.waypoint and not (self.waypoint.x == self.x and self.waypoint.y == self.y):
            if self.waypoint.y - self.y > 0:
                portrayal['angle'] = math.acos((self.waypoint.x - self.x) /
                                               np.linalg.norm((self.waypoint.x - self.x, self.waypoint.y - self.y)))
            else:
                portrayal['angle'] = 2 * math.pi - math.acos((self.waypoint.x - self.x) /
                                                             np.linalg.norm(
                                                                 (self.waypoint.x - self.x, self.waypoint.y - self.y)))
        else:
            portrayal['angle'] = 0
        return portrayal


class PlanetManager(CommunicatingAgent):
    def __init__(self, name: string, ships: List, unique_id: int, model, x, y):
        super().__init__(unique_id, model, name)
        self.x = x
        self.y = y
        self.items_to_ship = {}
        self.waiting_for_proposal = []
        self.ships = ships
        self.start_times = dict()
        self.proposals = dict()
        self.planets = []

    def step(self):
        if random.random() < NEW_ITEM_PROBA:
            item = Item(self.x, self.y)
            self.model.items.append(item)
            self.items_to_ship[item] = random.choice(self.planets)
        for item in self.items_to_ship:
            cfps = [spade.message.Message(to=str(a.communicator.jid),
                                          sender=str(self.communicator.jid),
                                          body=json.dumps(item.__dict__) + ',' +
                                               str(self.items_to_ship[item].x) + ',' + str(self.items_to_ship[item].y),
                                          thread='CNP-' + str(item),
                                          metadata={"performative": "call_for_proposal",
                                                    "turn": str(self.model.schedule.steps)}) for
                    a in self.ships if a.x == self.x and a.y == self.y]
            for c in cfps:
                self.send(c)
            self.start_times[item] = self.model.schedule.steps
            self.proposals[item] = []
            self.waiting_for_proposal.append(item)
        self.items_to_ship = dict()

        for i in [item for item in self.waiting_for_proposal if
                 self.model.schedule.steps - self.start_times[item] >= WAITING_TIME]:
            self.items_to_ship[i] = random.choice(self.planets)
            self.waiting_for_proposal.remove(i)
            del self.start_times[i]

        self.communicator.mutex.acquire()
        try:
            messages = [m for m in self.communicator.msg_box]
            self.communicator.msg_box = []
        finally:
            self.communicator.mutex.release()

        list_m = []
        i = 0
        index = 0
        for m in messages:
            if float(m.body) > i:
                i = float(m.body)
                index = len(list_m)
            list_m.append(float(m.body))

        if not len(list_m) == 0:
            for j in range(0, len(messages)):
                sender = messages[j].sender

                if not j == index:

                    reject_proposal = spade.message.Message(to=str(sender),
                                                            sender=str(self.communicator.jid),
                                                            body=str(1),
                                                            thread='reject_proposal-' + str(self.communicator.jid),
                                                            metadata={"performative": "reject_proposal",
                                                                      "turn": str(self.model.schedule.steps)})
                    self.send(reject_proposal)

                else:
                    accept_proposal = spade.message.Message(to=str(sender),
                                                            sender=str(self.communicator.jid),
                                                            body=str(1),
                                                            thread='accept_proposal-' + str(self.communicator.jid),
                                                            metadata={"performative": "accept_proposal",
                                                                      "turn": str(self.model.schedule.steps)})
                    self.send(accept_proposal)
                    self.waiting_for_proposal = []

    @staticmethod
    def portrayal_method():
        color = "blue"
        r = 6
        portrayal = {"Shape": "circle",
                     "Filled": "true",
                     "Layer": 1,
                     "Color": color,
                     "r": r}
        return portrayal


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
        if instantiate:
            new_element = ("new Simple_Continuous_Module({}, {},'{}')".
                           format(self.canvas_width, self.canvas_height, self.identifier))
            self.js_code = "elements.push(" + new_element + ");"

    @staticmethod
    def portrayal_method(obj):
        return obj.portrayal_method()

    def render(self, model):
        representation = defaultdict(list)
        for obj in model.schedule.agents:
            portrayal = self.portrayal_method(obj)
            if portrayal:
                if isinstance(obj, SpaceRoadNetwork):
                    for p in portrayal:
                        representation[p["Layer"]].append(p)
                else:
                    portrayal["x"] = ((obj.x - model.space.x_min) /
                                      (model.space.x_max - model.space.x_min))
                    portrayal["y"] = ((obj.y - model.space.y_min) /
                                      (model.space.y_max - model.space.y_min))
                    representation[portrayal["Layer"]].append(portrayal)
        for obj in model.items:
            portrayal = self.portrayal_method(obj)
            portrayal["x"] = ((obj.x - model.space.x_min) /
                              (model.space.x_max - model.space.x_min))
            portrayal["y"] = ((obj.y - model.space.y_min) /
                              (model.space.y_max - model.space.y_min))
            representation[portrayal["Layer"]].append(portrayal)
        return representation


class SpaceRoadNetwork(Agent):
    def __init__(self, planets: List[PlanetManager], unique_id: int, model: Model):
        super().__init__(unique_id, model)
        self.initial_graph = nx.Graph()
        self.current_graph = nx.Graph()
        self.speed_modificator = dict()
        for i in range(len(planets)):
            self.initial_graph.add_node(planets[i])
            for j in range(i):
                if random.random() < ROAD_BRANCHING_FACTOR:
                    distance = np.linalg.norm([planets[i].x - planets[j].x, planets[i].y - planets[j].y])
                    self.initial_graph.add_edge(planets[i], planets[j], distance=distance)
        # Reconnect graph of the roads between planets
        while len(list(nx.connected_components(self.initial_graph))) != 1:
            first_element = random.choice(tuple(list(nx.connected_components(self.initial_graph))[0]))
            second_element = random.choice(tuple(list(nx.connected_components(self.initial_graph))[1]))
            distance = np.linalg.norm([first_element.x - second_element.x, first_element.y - second_element.y])
            self.initial_graph.add_edge(first_element, second_element, distance=distance)
        for e in self.initial_graph.edges:
            self.current_graph.add_edge(e[0], e[1],
                                        distance=nx.get_edge_attributes(self.initial_graph, 'distance')[(e[0], e[1])])
            self.speed_modificator[e] = 1.0
            self.speed_modificator[(e[1], e[0])] = 1.0
        print('foo')

    def step(self):
        for e in self.current_graph.edges:
            if random.random() < PROBA_ISSUE_ROAD:
                a = [0, 1]
                if self.speed_modificator[e] == 0:
                    a[0] = 0.5
                elif self.speed_modificator[e] == 1:
                    a[1] = 0.5

                self.speed_modificator[e] = a[int(random.random() > 0.5)]

    def portrayal_method(self):
        portrayals = []
        for e in [edge for edge in self.current_graph.edges]:
            if self.speed_modificator[e] != 0:
                if self.speed_modificator[e] == 1:
                    color = "green"
                else:
                    color = "red"
                portrayal = {"Shape": "line",
                             "width": 1,
                             "Layer": 1,
                             "Color": color,
                             "from_x": (tuple(e)[0].x - self.model.space.x_min) /
                                       (self.model.space.x_max - self.model.space.x_min),
                             "from_y": (tuple(e)[0].y - self.model.space.y_min) /
                                       (self.model.space.y_max - self.model.space.y_min),
                             "to_x": (tuple(e)[1].x - self.model.space.x_min) /
                                     (self.model.space.x_max - self.model.space.x_min),
                             "to_y": (tuple(e)[1].y - self.model.space.y_min) /
                                     (self.model.space.y_max - self.model.space.y_min)
                             }
                portrayals.append(portrayal)
        return portrayals


def run_single_server():
    chart = ChartModule([{"Label": "items",
                          "Color": "Red"},
                         {"Label": "Delivered",
                          "Color": "Blue"}
                         ],
                        data_collector_name='datacollector')

    server = ModularServer(PlanetDelivery,
                           [ContinuousCanvas(), chart],
                           "PlanetDelivery",
                           {"n_planets": ModularVisualization.UserSettableParameter('slider',
                                                                                    "Number of planets",
                                                                                    10, 3, 20, 1),
                            "n_ships": ModularVisualization.UserSettableParameter('slider',
                                                                                  "Number of spaceships",
                                                                                  15, 3, 30, 1)})
    server.port = 8521
    server.launch()


if __name__ == "__main__":
    run_single_server()

