# Third party imports
import networkx as nx
import numpy as np

# Project imports
from Request_generator import Generate
from load_input import load_input
from SDN_Controller import controller_main


class Engine:
    """
    Update
    """

    def __init__(self):
        self.blocking = dict()
        self.blocking_iter = 0
        self.sim_input = None

        self.network_spec_db = dict()
        self.physical_topology = nx.Graph()

        self.requests = None
        self.sorted_requests = None
        self.requests_status = dict()

    def update_blocking(self, i):
        """
        Update
        :param i:
        :return:
        """
        self.blocking.update({i: self.blocking_iter / self.sim_input['number_of_request']})

    def handle_arrival(self, time):
        """
        Update
        :param time:
        :return:
        """
        rsa_res = controller_main(src=self.sorted_requests[time]["source"][0],
                                  dest=self.sorted_requests[time]["destination"][0],
                                  request_type="Arrival",
                                  Physical_topology=self.physical_topology,
                                  network_spectrum_DB=self.network_spec_db,
                                  slots_needed=self.requests[time]['number_of_slot'][0],
                                  slot_NO=-1,
                                  path=list()
                                  )
        if rsa_res is False:
            self.blocking_iter += 1
        else:
            self.requests_status.update({self.sorted_requests[time]['id']: {
                "slots": rsa_res[0]['starting_NO_reserved_slot'],
                "path": rsa_res[0]['path']
            }})
            self.network_spec_db = rsa_res[1]
            self.physical_topology = rsa_res[2]

    def handle_release(self, time):
        """
        Update
        :param time:
        :return:
        """
        if self.sorted_requests[time]['id'] in self.requests_status:
            controller_main(src=self.sorted_requests[time]["source"][0],
                            dest=self.sorted_requests[time]["destination"][0],
                            request_type="Release",
                            Physical_topology=self.physical_topology,
                            network_spectrum_DB=self.network_spec_db,
                            slots_needed=self.requests[time]['number_of_slot'][0],
                            slot_NO=self.requests_status[self.sorted_requests[time]['id']]['slots'],
                            path=self.requests_status[self.sorted_requests[time]['id']]['path']
                            )

    def create_pt(self):
        """
        Update
        :return:
        """
        for node in self.sim_input['physical_topology']['nodes']:
            self.physical_topology.add_node(node)

        for link_no in self.sim_input['physical_topology']['links']:
            self.network_spec_db.update({(self.sim_input['physical_topology']['links'][link_no]['source'],
                                          self.sim_input['physical_topology']['links'][link_no]['destination']):
                                             np.zeros((self.sim_input['physical_topology']['links']
                                                       [link_no]['fiber']['num_cores'],
                                                       self.sim_input['number_of_slot_per_lisnk']))})

            self.physical_topology.add_edge(self.sim_input['physical_topology']['links'][link_no]['source'],
                                            self.sim_input['physical_topology']['links'][link_no]['destination'],
                                            length=self.sim_input['physical_topology']['links'][link_no]['length'])

    def load_input(self):
        """
        Update
        :return:
        """
        self.sim_input = load_input()

    def run(self):
        """
        Update
        :return:
        """
        self.load_input()

        for i in range(self.sim_input['NO_iteration']):
            self.blocking_iter = 0
            self.requests_status = dict()
            self.create_pt()

            self.requests = Generate(seed_no=self.sim_input['seed'],
                                     nodes=list(self.sim_input['physical_topology']['nodes'].keys()),
                                     holding_time_mean=self.sim_input['holding_time_mean'],
                                     inter_arrival_time_mean=self.sim_input['inter_arrival_time'],
                                     req_no=self.sim_input['number_of_request'],
                                     slot_list=self.sim_input['BW_type'])

            self.sorted_requests = dict(sorted(self.requests.items()))

            for time in self.sorted_requests:
                if self.sorted_requests[time]['request_type'] == "Arrival":
                    self.handle_arrival(time)
                elif self.sorted_requests[time]['request_type'] == "Release":
                    self.handle_arrival(time)

            self.update_blocking(i)
            print("Here")


if __name__ == '__main__':
    obj_one = Engine()
    obj_one.run()
